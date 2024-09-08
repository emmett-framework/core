use pyo3::prelude::*;
use std::collections::HashMap;

mod http;
mod ws;

type RouteMapStatic = HashMap<Box<str>, PyObject>;
type RouteMapMatch = Vec<(regex::Regex, Vec<Box<str>>, PyObject)>;

#[derive(Default)]
struct RouteMap {
    r#static: RouteMapStatic,
    r#match: RouteMapMatch,
}

macro_rules! get_route_tree {
    ($rmapty:tt, $routes:expr, $host:expr, $scheme:expr) => {{
        let node_host = match $host {
            Some(host) => match $routes.whost.get_mut(host) {
                Some(v) => v,
                None => {
                    let mut node: HashMap<Box<str>, $rmapty> = HashMap::with_capacity($routes.whost.len() + 1);
                    let keys: Vec<Box<str>> = $routes.whost.keys().map(|v| v.clone()).collect();
                    for key in keys {
                        node.insert(key.clone(), $routes.whost.remove(&key).unwrap());
                    }
                    node.insert(host.into(), $rmapty::default());
                    $routes.whost = node;
                    $routes.whost.get_mut(host).unwrap()
                }
            },
            None => &mut $routes.nhost,
        };
        match $scheme {
            Some("secure") => &mut node_host.secure,
            Some("plain") => &mut node_host.plain,
            _ => &mut node_host.any,
        }
    }};
}

macro_rules! match_scheme_route_tree {
    ($scheme:expr, $target:expr) => {
        match $scheme {
            "https" => &$target.secure,
            "http" => &$target.plain,
            _ => unreachable!(),
        }
    };
}

use get_route_tree;
use match_scheme_route_tree;

pub(crate) fn init_pymodule(module: &Bound<PyModule>) -> PyResult<()> {
    module.add_class::<http::HTTPRouter>()?;
    module.add_class::<ws::WSRouter>()?;

    Ok(())
}
