//! Accepts heartbeats from agents and lists them at GET /.
//!
//!   curl http://<control-plane>:8080/

use std::collections::HashMap;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::{Arc, Mutex};
use std::time::Instant;
use std::{env, thread};

type Agents = Arc<Mutex<HashMap<String, Instant>>>;

fn main() -> std::io::Result<()> {
    let listen = arg_value("--listen").unwrap_or_else(|| "0.0.0.0:8080".into());
    let listener = TcpListener::bind(&listen)?;
    let agents: Agents = Arc::default();
    println!("controller listening on {listen}");

    for stream in listener.incoming().flatten() {
        let agents = Arc::clone(&agents);
        thread::spawn(move || {
            if let Err(e) = handle(stream, &agents) {
                eprintln!("request failed: {e}");
            }
        });
    }
    Ok(())
}

fn handle(mut stream: TcpStream, agents: &Agents) -> std::io::Result<()> {
    let mut reader = BufReader::new(stream.try_clone()?);
    let mut request_line = String::new();
    reader.read_line(&mut request_line)?;

    let mut content_length = 0;
    loop {
        let mut header = String::new();
        if reader.read_line(&mut header)? == 0 || header == "\r\n" {
            break;
        }
        if let Some(v) = header.to_ascii_lowercase().strip_prefix("content-length:") {
            content_length = v.trim().parse().unwrap_or(0);
        }
    }
    let mut body = vec![0; content_length.min(1024)];
    reader.read_exact(&mut body)?;

    let response = if request_line.starts_with("POST /heartbeat") {
        let node = String::from_utf8_lossy(&body).trim().to_string();
        if agents.lock().unwrap().insert(node.clone(), Instant::now()).is_none() {
            println!("new agent: {node}");
        }
        "ok\n".to_string()
    } else {
        let agents = agents.lock().unwrap();
        let mut names: Vec<_> = agents.keys().collect();
        names.sort();
        let mut out = format!("{} agent(s)\n", names.len());
        for name in names {
            out += &format!("  {name:<16} last seen {}s ago\n", agents[name].elapsed().as_secs());
        }
        out
    };
    write!(
        stream,
        "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{response}",
        response.len()
    )
}

fn arg_value(flag: &str) -> Option<String> {
    let args: Vec<String> = env::args().collect();
    args.iter().position(|a| a == flag).and_then(|i| args.get(i + 1).cloned())
}
