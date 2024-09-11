use anyhow::Result;
use pyo3::{prelude::*, types::PyDict};
use std::collections::HashMap;

use super::{get_route_tree, match_re_routes, match_scheme_route_tree, ReGroupType, RouteMap, RouteMapMatch};

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
        routes.r#static.get(path).map_or_else(
            || match_re_routes!(py, routes, path),
            |route| Some((route.clone_ref(py), pydict.clone_ref(py))),
        )
    }
}

#[pymethods]
impl WSRouter {
    #[new]
    #[pyo3(signature = (*_args, **_kwargs))]
    fn new(py: Python, _args: &Bound<PyAny>, _kwargs: Option<&Bound<PyAny>>) -> Self {
        Self {
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

    #[pyo3(signature = (route, rule, rgtmap, host=None, scheme=None))]
    fn add_re_route(
        &mut self,
        route: PyObject,
        rule: &str,
        rgtmap: &Bound<PyDict>,
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
            .or_else(|| Some((self.pynone.clone_ref(py), self.pydict.clone_ref(py))))
            .unwrap()
    }

    #[pyo3(signature = (scheme, path))]
    fn match_route_scheme(&self, py: Python, scheme: &str, path: &str) -> (PyObject, PyObject) {
        WSRouter::match_routes(
            py,
            &self.pydict,
            match_scheme_route_tree!(scheme, self.routes.nhost),
            path,
        )
        .or_else(|| WSRouter::match_routes(py, &self.pydict, &self.routes.nhost.any, path))
        .or_else(|| Some((self.pynone.clone_ref(py), self.pydict.clone_ref(py))))
        .unwrap()
    }

    #[pyo3(signature = (host, path))]
    fn match_route_host(&self, py: Python, host: &str, path: &str) -> (PyObject, PyObject) {
        self.routes
            .whost
            .get(host)
            .map_or_else(
                || WSRouter::match_routes(py, &self.pydict, &self.routes.nhost.any, path),
                |routes_node| {
                    WSRouter::match_routes(py, &self.pydict, &routes_node.any, path)
                        .or_else(|| WSRouter::match_routes(py, &self.pydict, &self.routes.nhost.any, path))
                },
            )
            .or_else(|| Some((self.pynone.clone_ref(py), self.pydict.clone_ref(py))))
            .unwrap()
    }

    #[pyo3(signature = (host, scheme, path))]
    fn match_route_all(&self, py: Python, host: &str, scheme: &str, path: &str) -> (PyObject, PyObject) {
        self.routes
            .whost
            .get(host)
            .map_or_else(
                || {
                    WSRouter::match_routes(
                        py,
                        &self.pydict,
                        match_scheme_route_tree!(scheme, self.routes.nhost),
                        path,
                    )
                    .or_else(|| WSRouter::match_routes(py, &self.pydict, &self.routes.nhost.any, path))
                },
                |routes_node| {
                    WSRouter::match_routes(py, &self.pydict, match_scheme_route_tree!(scheme, routes_node), path)
                        .or_else(|| {
                            WSRouter::match_routes(py, &self.pydict, &routes_node.any, path).or_else(|| {
                                WSRouter::match_routes(
                                    py,
                                    &self.pydict,
                                    match_scheme_route_tree!(scheme, &self.routes.nhost),
                                    path,
                                )
                                .or_else(|| WSRouter::match_routes(py, &self.pydict, &self.routes.nhost.any, path))
                            })
                        })
                },
            )
            .or_else(|| Some((self.pynone.clone_ref(py), self.pydict.clone_ref(py))))
            .unwrap()
    }
}
