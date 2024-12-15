use pyo3::prelude::*;
use std::collections::HashMap;

mod http;
mod parse;
mod ws;

type RouteMapStatic = HashMap<Box<str>, PyObject>;
type RouteMapMatch = Vec<(regex::Regex, Vec<(Box<str>, ReGroupType)>, PyObject)>;

enum ReGroupType {
    Any,
    Int,
    Float,
    Date,
}

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

macro_rules! match_re_routes {
    ($py:expr, $routes:expr, $path:expr) => {{
        $py.allow_threads(|| {
            for (rpath, groupnames, robj) in &$routes.r#match {
                if rpath.is_match($path) {
                    let groups = rpath.captures($path).unwrap();
                    return Some((robj, groupnames, groups));
                }
            }
            None
        })
        .and_then(|(route, gnames, mgroups)| {
            let pydict = PyDict::new($py);
            for (gname, gtype) in gnames {
                let gval = mgroups.name(gname).map_or_else(
                    || Ok($py.None()),
                    |v| {
                        let vstr = v.as_str();
                        match gtype {
                            ReGroupType::Int => super::parse::parse_int_arg($py, vstr),
                            ReGroupType::Float => super::parse::parse_float_arg($py, vstr),
                            ReGroupType::Date => super::parse::parse_date_arg($py, vstr),
                            _ => Ok(vstr.into_py_any($py)?),
                        }
                    },
                );
                if gval.is_err() {
                    return None;
                }
                let _ = pydict.set_item(&gname[..], gval.unwrap());
            }
            return Some((route.clone_ref($py), pydict.into_py_any($py).unwrap()));
        })
    }};
}

use get_route_tree;
use match_re_routes;
use match_scheme_route_tree;

pub(crate) fn init_pymodule(module: &Bound<PyModule>) -> PyResult<()> {
    module.add_class::<http::HTTPRouter>()?;
    module.add_class::<ws::WSRouter>()?;

    Ok(())
}
