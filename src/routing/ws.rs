use anyhow::Result;
use pyo3::{prelude::*, types::PyDict};
use std::{collections::HashMap, convert::identity};

use super::{get_route_tree, match_scheme_route_tree, RouteMap, RouteMapMatch};

#[derive(Default)]
struct WSRouteMap {
    any: RouteMap,
    plain: RouteMap,
    secure: RouteMap,
}

struct WSRouterData {
    nhost: WSRouteMap,
    whost: HashMap<Box<str>, WSRouteMap>,
}

#[pyclass(module = "emmett_core._emmett_core", subclass)]
pub(super) struct WSRouter {
    #[pyo3(get)]
    app: PyObject,
    #[pyo3(get)]
    current: PyObject,
    routes: WSRouterData,
    pydict: PyObject,
    pynone: PyObject,
}

impl WSRouter {
    #[inline]
    fn match_routes<'p>(
        py: Python<'p>,
        pydict: &PyObject,
        routes: &'p RouteMap,
        path: &str,
    ) -> Option<(PyObject, PyObject)> {
        match routes.r#static.get(path) {
            Some(route) => Some((route.clone_ref(py), pydict.clone_ref(py))),
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
                None
            }
        }
    }
}

#[pymethods]
impl WSRouter {
    #[new]
    fn new(py: Python, app: PyObject, current: PyObject) -> Self {
        Self {
            app,
            current,
            pydict: PyDict::new_bound(py).into(),
            pynone: py.None(),
            routes: WSRouterData {
                nhost: WSRouteMap::default(),
                whost: HashMap::new(),
            },
        }
    }

    #[pyo3(signature = (route, path, host=None, scheme=None))]
    fn add_static_route(&mut self, route: PyObject, path: &str, host: Option<&str>, scheme: Option<&str>) {
        let node_method = get_route_tree!(WSRouteMap, self.routes, host, scheme);
        let mut node: HashMap<Box<str>, PyObject> = HashMap::with_capacity(node_method.r#static.len() + 1);
        let keys: Vec<Box<str>> = node_method.r#static.keys().cloned().collect();
        for key in keys {
            node.insert(key.clone(), node_method.r#static.remove(&key).unwrap());
        }
        node.insert(path.into(), route);
        node_method.r#static = node;
    }

    #[pyo3(signature = (route, rule, host=None, scheme=None))]
    fn add_re_route(&mut self, route: PyObject, rule: &str, host: Option<&str>, scheme: Option<&str>) -> Result<()> {
        let re = regex::Regex::new(rule)?;
        let mut re_groups = re.capture_names();
        re_groups.next();
        let groups: Vec<Box<str>> = re_groups.flatten().map(std::convert::Into::into).collect();
        let node_method = get_route_tree!(WSRouteMap, self.routes, host, scheme);
        let mut nodec: RouteMapMatch = Vec::with_capacity(node_method.r#match.len() + 1);
        nodec.push((re, groups, route));
        while let Some(v) = node_method.r#match.pop() {
            nodec.push(v);
        }
        let node: RouteMapMatch = nodec.into_iter().rev().collect();
        node_method.r#match = node;
        Ok(())
    }

    #[pyo3(signature = (path))]
    fn match_route_direct(&self, py: Python, path: &str) -> (PyObject, PyObject) {
        WSRouter::match_routes(py, &self.pydict, &self.routes.nhost.any, path)
            .map_or_else(|| (self.pynone.clone_ref(py), self.pydict.clone_ref(py)), identity)
    }

    #[pyo3(signature = (scheme, path))]
    fn match_route_scheme(&self, py: Python, scheme: &str, path: &str) -> (PyObject, PyObject) {
        match WSRouter::match_routes(
            py,
            &self.pydict,
            match_scheme_route_tree!(scheme, self.routes.nhost),
            path,
        ) {
            None => WSRouter::match_routes(py, &self.pydict, &self.routes.nhost.any, path),
            v => v,
        }
        .map_or_else(|| (self.pynone.clone_ref(py), self.pydict.clone_ref(py)), identity)
    }

    #[pyo3(signature = (host, path))]
    fn match_route_host(&self, py: Python, host: &str, path: &str) -> (PyObject, PyObject) {
        match self.routes.whost.get(host) {
            Some(routes_node) => match WSRouter::match_routes(py, &self.pydict, &routes_node.any, path) {
                None => WSRouter::match_routes(py, &self.pydict, &self.routes.nhost.any, path),
                v => v,
            },
            None => WSRouter::match_routes(py, &self.pydict, &self.routes.nhost.any, path),
        }
        .map_or_else(|| (self.pynone.clone_ref(py), self.pydict.clone_ref(py)), identity)
    }

    #[pyo3(signature = (host, scheme, path))]
    fn match_route_all(&self, py: Python, host: &str, scheme: &str, path: &str) -> (PyObject, PyObject) {
        match self.routes.whost.get(host) {
            Some(routes_node) => {
                match WSRouter::match_routes(py, &self.pydict, match_scheme_route_tree!(scheme, routes_node), path) {
                    None => WSRouter::match_routes(py, &self.pydict, &routes_node.any, path),
                    v => v,
                }
            }
            None => {
                match WSRouter::match_routes(
                    py,
                    &self.pydict,
                    match_scheme_route_tree!(scheme, self.routes.nhost),
                    path,
                ) {
                    None => WSRouter::match_routes(py, &self.pydict, &self.routes.nhost.any, path),
                    v => v,
                }
            }
        }
        .map_or_else(|| (self.pynone.clone_ref(py), self.pydict.clone_ref(py)), identity)
    }
}
