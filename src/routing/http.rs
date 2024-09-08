use anyhow::Result;
use pyo3::{prelude::*, types::PyDict};
use std::{collections::HashMap, convert::identity};

use super::{get_route_tree, match_scheme_route_tree, RouteMap, RouteMapMatch};

type HTTPRouteMapNode = HashMap<Box<str>, RouteMap>;

#[derive(Default)]
struct HTTPRouteMap {
    any: HTTPRouteMapNode,
    plain: HTTPRouteMapNode,
    secure: HTTPRouteMapNode,
}

struct HTTPRouterData {
    nhost: HTTPRouteMap,
    whost: HashMap<Box<str>, HTTPRouteMap>,
}

macro_rules! get_route_node_mut {
    ($routes:expr, $host:expr, $scheme:expr, $method:expr) => {{
        let node_scheme = get_route_tree!(HTTPRouteMap, $routes, $host, $scheme);
        match node_scheme.get_mut($method) {
            Some(v) => v,
            None => {
                let mut node: HTTPRouteMapNode = HashMap::with_capacity(node_scheme.len() + 1);
                let keys: Vec<Box<str>> = node_scheme.keys().map(|v| v.clone()).collect();
                for key in keys {
                    node.insert(key.clone(), node_scheme.remove(&key).unwrap());
                }
                node.insert($method.into(), RouteMap::default());
                *node_scheme = node;
                node_scheme.get_mut($method).unwrap()
            }
        }
    }};
}

#[pyclass(module = "emmett_core._emmett_core", subclass)]
pub(super) struct HTTPRouter {
    // #[pyo3(get)]
    // app: PyObject,
    // #[pyo3(get)]
    // current: PyObject,
    routes: HTTPRouterData,
    pydict: PyObject,
    pynone: PyObject,
}

impl HTTPRouter {
    #[inline]
    fn match_routes<'p>(
        py: Python<'p>,
        pydict: &PyObject,
        routes_node: &'p HTTPRouteMapNode,
        method: &str,
        path: &str,
    ) -> Option<(PyObject, PyObject)> {
        if let Some(routes) = routes_node.get(method) {
            match routes.r#static.get(path) {
                Some(route) => return Some((route.clone_ref(py), pydict.clone_ref(py))),
                None => {
                    if let Some((route, gnames, mgroups)) = py.allow_threads(|| {
                        for (rpath, groupnames, robj) in &routes.r#match {
                            if rpath.is_match(path) {
                                let groups = rpath.captures(path).unwrap();
                                return Some((robj, groupnames, groups));
                            }
                        }
                        None
                    }) {
                        let pydict = PyDict::new_bound(py);
                        for gname in gnames {
                            let _ = pydict.set_item(&gname[..], mgroups.name(gname).map(|v| v.as_str()));
                        }
                        return Some((route.clone_ref(py), pydict.into_py(py)));
                    }
                }
            }
        }
        None
    }
}

#[pymethods]
impl HTTPRouter {
    #[new]
    #[pyo3(signature = (*_args, **_kwargs))]
    fn new(py: Python, _args: &Bound<PyAny>, _kwargs: Option<&Bound<PyAny>>) -> Self {
        Self {
            pydict: PyDict::new_bound(py).into(),
            pynone: py.None(),
            routes: HTTPRouterData {
                nhost: HTTPRouteMap::default(),
                whost: HashMap::new(),
            },
        }
    }

    #[pyo3(signature = (route, path, method, host=None, scheme=None))]
    fn add_static_route(
        &mut self,
        route: PyObject,
        path: &str,
        method: &str,
        host: Option<&str>,
        scheme: Option<&str>,
    ) {
        let node_method = get_route_node_mut!(self.routes, host, scheme, method);
        let mut node: HashMap<Box<str>, PyObject> = HashMap::with_capacity(node_method.r#static.len() + 1);
        let keys: Vec<Box<str>> = node_method.r#static.keys().cloned().collect();
        for key in keys {
            node.insert(key.clone(), node_method.r#static.remove(&key).unwrap());
        }
        node.insert(path.into(), route);
        node_method.r#static = node;
    }

    #[pyo3(signature = (route, rule, method, host=None, scheme=None))]
    fn add_re_route(
        &mut self,
        route: PyObject,
        rule: &str,
        method: &str,
        host: Option<&str>,
        scheme: Option<&str>,
    ) -> Result<()> {
        let re = regex::Regex::new(rule)?;
        let mut re_groups = re.capture_names();
        re_groups.next();
        let groups: Vec<Box<str>> = re_groups.flatten().map(std::convert::Into::into).collect();
        let node_method = get_route_node_mut!(self.routes, host, scheme, method);
        let mut nodec: RouteMapMatch = Vec::with_capacity(node_method.r#match.len() + 1);
        nodec.push((re, groups, route));
        while let Some(v) = node_method.r#match.pop() {
            nodec.push(v);
        }
        let node: RouteMapMatch = nodec.into_iter().rev().collect();
        node_method.r#match = node;
        Ok(())
    }

    #[pyo3(signature = (method, path))]
    fn match_route_direct(&self, py: Python, method: &str, path: &str) -> (PyObject, PyObject) {
        HTTPRouter::match_routes(py, &self.pydict, &self.routes.nhost.any, method, path)
            .map_or_else(|| (self.pynone.clone_ref(py), self.pydict.clone_ref(py)), identity)
    }

    #[pyo3(signature = (scheme, method, path))]
    fn match_route_scheme(&self, py: Python, scheme: &str, method: &str, path: &str) -> (PyObject, PyObject) {
        match HTTPRouter::match_routes(
            py,
            &self.pydict,
            match_scheme_route_tree!(scheme, self.routes.nhost),
            method,
            path,
        ) {
            None => HTTPRouter::match_routes(py, &self.pydict, &self.routes.nhost.any, method, path),
            v => v,
        }
        .map_or_else(|| (self.pynone.clone_ref(py), self.pydict.clone_ref(py)), identity)
    }

    #[pyo3(signature = (host, method, path))]
    fn match_route_host(&self, py: Python, host: &str, method: &str, path: &str) -> (PyObject, PyObject) {
        match self.routes.whost.get(host) {
            Some(routes_node) => match HTTPRouter::match_routes(py, &self.pydict, &routes_node.any, method, path) {
                None => HTTPRouter::match_routes(py, &self.pydict, &self.routes.nhost.any, method, path),
                v => v,
            },
            None => HTTPRouter::match_routes(py, &self.pydict, &self.routes.nhost.any, method, path),
        }
        .map_or_else(|| (self.pynone.clone_ref(py), self.pydict.clone_ref(py)), identity)
    }

    #[pyo3(signature = (host, scheme, method, path))]
    fn match_route_all(&self, py: Python, host: &str, scheme: &str, method: &str, path: &str) -> (PyObject, PyObject) {
        match self.routes.whost.get(host) {
            Some(routes_node) => {
                match HTTPRouter::match_routes(
                    py,
                    &self.pydict,
                    match_scheme_route_tree!(scheme, routes_node),
                    method,
                    path,
                ) {
                    None => HTTPRouter::match_routes(py, &self.pydict, &routes_node.any, method, path),
                    v => v,
                }
            }
            None => {
                match HTTPRouter::match_routes(
                    py,
                    &self.pydict,
                    match_scheme_route_tree!(scheme, self.routes.nhost),
                    method,
                    path,
                ) {
                    None => HTTPRouter::match_routes(py, &self.pydict, &self.routes.nhost.any, method, path),
                    v => v,
                }
            }
        }
        .map_or_else(|| (self.pynone.clone_ref(py), self.pydict.clone_ref(py)), identity)
    }
}
