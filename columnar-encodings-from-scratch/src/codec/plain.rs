use super::{Encoded, Item, Values};
use crate::bits::{put_varint, Reader, Res};

pub fn encode(v: &Values) -> Encoded {
    let mut out = Vec::with_capacity(v.raw_bytes() + 8);
    put_varint(&mut out, v.len() as u64);
    match v {
        Values::Int(x) => x.iter().for_each(|i| out.extend_from_slice(&i.to_le_bytes())),
        Values::Float(x) => x.iter().for_each(|f| out.extend_from_slice(&f.to_le_bytes())),
        Values::Str(x) => x.iter().for_each(|s| s.put(&mut out)),
    }
    Encoded { bytes: out, detail: "values written as they are: 8 bytes per number, length + bytes per string".into() }
}

pub fn decode(r: &mut Reader, kind: &str) -> Res<Values> {
    let n = r.len()?;
    Ok(match kind {
        "int" => Values::Int((0..n).map(|_| r.u64().map(|u| u as i64)).collect::<Res<_>>()?),
        "float" => Values::Float((0..n).map(|_| r.u64().map(f64::from_bits)).collect::<Res<_>>()?),
        _ => Values::Str((0..n).map(|_| String::get(r)).collect::<Res<_>>()?),
    })
}
