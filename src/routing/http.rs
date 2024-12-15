use anyhow::Result;
use pyo3::{prelude::*, types::PyDict, IntoPyObjectExt};
use std::{collections::HashMap, sync::RwLock};

use super::{get_route_tree, match_re_routes, match_scheme_route_tree, ReGroupType, RouteMap, RouteMapMatch};

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

#[pyclass(module = "emmett_core._emmett_core", frozen, subclass)]
pub(super) struct HTTPRouter {
    routes: RwLock<HTTPRouterData>,
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
        routes_node.get(method).and_then(|routes| {
            routes.r#static.get(path).map_or_else(
                || match_re_routes!(py, routes, path),
                |route| Some((route.clone_ref(py), pydict.clone_ref(py))),
            )
        })
    }
}

#[pymethods]
impl HTTPRouter {
    #[new]
    #[pyo3(signature = (*_args, **_kwargs))]
    fn new(py: Python, _args: &Bound<PyAny>, _kwargs: Option<&Bound<PyAny>>) -> Self {
        Self {
            pydict: PyDict::new(py).into(),
            pynone: py.None(),
            routes: RwLock::new(HTTPRouterData {
                nhost: HTTPRouteMap::default(),
                whost: HashMap::new(),
            }),
        }
    }

    #[pyo3(signature = (route, path, method, host=None, scheme=None))]
    fn add_static_route(&self, route: PyObject, path: &str, method: &str, host: Option<&str>, scheme: Option<&str>) {
        let mut routes = self.routes.write().unwrap();
        let node_method = get_route_node_mut!(routes, host, scheme, method);
        let mut node: HashMap<Box<str>, PyObject> = HashMap::with_capacity(node_method.r#static.len() + 1);
        let keys: Vec<Box<str>> = node_method.r#static.keys().cloned().collect();
        for key in keys {
            node.insert(key.clone(), node_method.r#static.remove(&key).unwrap());
        }
        node.insert(path.into(), route);
        node_method.r#static = node;
    }

    #[pyo3(signature = (route, rule, rgtmap, method, host=None, scheme=None))]
    fn add_re_route(
        &self,
        route: PyObject,
        rule: &str,
        rgtmap: &Bound<PyDict>,
        method: &str,
        host: Option<&str>,
        scheme: Option<&str>,
    ) -> Result<()> {
        let re = regex::Regex::new(rule)?;
        let mut re_groups = re.capture_names();
        re_groups.next();
        let groupsn: Vec<&str> = re_groups.flatten().collect();
        let mut groups: Vec<(Box<str>, ReGroupType)> = Vec::with_capacity(groupsn.len());
        for key in groupsn {
            let atype = match rgtmap.get_item(key)? {
                Some(mapv) => {
                    let atype = mapv.extract::<String>()?;
                    match &atype[..] {
                        "int" => ReGroupType::Int,
                        "float" => ReGroupType::Float,
                        "date" => ReGroupType::Date,
                        _ => ReGroupType::Any,
                    }
                }
                _ => ReGroupType::Any,
            };
            groups.push((key.into(), atype));
        }
        let mut routes = self.routes.write().unwrap();
        let node_method = get_route_node_mut!(routes, host, scheme, method);
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
        let routes = self.routes.read().unwrap();
        HTTPRouter::match_routes(py, &self.pydict, &routes.nhost.any, method, path)
            .or_else(|| Some((self.pynone.clone_ref(py), self.pydict.clone_ref(py))))
            .unwrap()
    }

    #[pyo3(signature = (scheme, method, path))]
    fn match_route_scheme(&self, py: Python, scheme: &str, method: &str, path: &str) -> (PyObject, PyObject) {
        let routes = self.routes.read().unwrap();
        HTTPRouter::match_routes(
            py,
            &self.pydict,
            match_scheme_route_tree!(scheme, routes.nhost),
            method,
            path,
        )
        .or_else(|| HTTPRouter::match_routes(py, &self.pydict, &routes.nhost.any, method, path))
        .or_else(|| Some((self.pynone.clone_ref(py), self.pydict.clone_ref(py))))
        .unwrap()
    }

    #[pyo3(signature = (host, method, path))]
    fn match_route_host(&self, py: Python, host: &str, method: &str, path: &str) -> (PyObject, PyObject) {
        let routes = self.routes.read().unwrap();
        routes
            .whost
            .get(host)
            .map_or_else(
                || HTTPRouter::match_routes(py, &self.pydict, &routes.nhost.any, method, path),
                |routes_node| {
                    HTTPRouter::match_routes(py, &self.pydict, &routes_node.any, method, path)
                        .or_else(|| HTTPRouter::match_routes(py, &self.pydict, &routes.nhost.any, method, path))
                },
            )
            .or_else(|| Some((self.pynone.clone_ref(py), self.pydict.clone_ref(py))))
            .unwrap()
    }

    #[pyo3(signature = (host, scheme, method, path))]
    fn match_route_all(&self, py: Python, host: &str, scheme: &str, method: &str, path: &str) -> (PyObject, PyObject) {
        let routes = self.routes.read().unwrap();
        routes
            .whost
            .get(host)
            .map_or_else(
                || {
                    HTTPRouter::match_routes(
                        py,
                        &self.pydict,
                        match_scheme_route_tree!(scheme, routes.nhost),
                        method,
                        path,
                    )
                    .or_else(|| HTTPRouter::match_routes(py, &self.pydict, &routes.nhost.any, method, path))
                },
                |routes_node| {
                    HTTPRouter::match_routes(
                        py,
                        &self.pydict,
                        match_scheme_route_tree!(scheme, routes_node),
                        method,
                        path,
                    )
                    .or_else(|| {
                        HTTPRouter::match_routes(py, &self.pydict, &routes_node.any, method, path).or_else(|| {
                            HTTPRouter::match_routes(
                                py,
                                &self.pydict,
                                match_scheme_route_tree!(scheme, &routes.nhost),
                                method,
                                path,
                            )
                            .or_else(|| HTTPRouter::match_routes(py, &self.pydict, &routes.nhost.any, method, path))
                        })
                    })
                },
            )
            .or_else(|| Some((self.pynone.clone_ref(py), self.pydict.clone_ref(py))))
            .unwrap()
    }
}
