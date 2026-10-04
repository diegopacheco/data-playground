pub mod alp;
pub mod bitpack;
pub mod delta;
pub mod dict;
pub mod fsst;
pub mod frame;
pub mod plain;
pub mod rle;

use crate::bits::{put_varint, Reader, Res};
use std::hash::Hash;

#[derive(Clone, Debug, PartialEq)]
pub enum Values {
    Int(Vec<i64>),
    Float(Vec<f64>),
    Str(Vec<String>),
}

pub struct Encoded {
    pub bytes: Vec<u8>,
    pub detail: String,
}

impl Values {
    pub fn kind(&self) -> &'static str {
        match self {
            Values::Int(_) => "int",
            Values::Float(_) => "float",
            Values::Str(_) => "str",
        }
    }

    pub fn len(&self) -> usize {
        match self {
            Values::Int(v) => v.len(),
            Values::Float(v) => v.len(),
            Values::Str(v) => v.len(),
        }
    }

    pub fn raw_bytes(&self) -> usize {
        match self {
            Values::Int(v) => v.len() * 8,
            Values::Float(v) => v.len() * 8,
            Values::Str(v) => v.iter().map(|s| s.len() + 4).sum(),
        }
    }

    pub fn same(&self, other: &Values) -> bool {
        match (self, other) {
            (Values::Float(a), Values::Float(b)) => a.len() == b.len() && a.iter().zip(b).all(|(x, y)| x.to_bits() == y.to_bits()),
            _ => self == other,
        }
    }
}

pub fn encodings(kind: &str) -> &'static [&'static str] {
    match kind {
        "int" => &["plain", "rle", "dict", "delta", "for", "bitpack"],
        "float" => &["plain", "rle", "dict", "alp"],
        _ => &["plain", "rle", "dict", "fsst"],
    }
}

pub fn encode(name: &str, v: &Values) -> Res<Encoded> {
    match (name, v) {
        ("plain", _) => Ok(plain::encode(v)),
        ("rle", Values::Int(x)) => Ok(rle::encode(x)),
        ("rle", Values::Float(x)) => Ok(rle::encode(&to_bits(x))),
        ("rle", Values::Str(x)) => Ok(rle::encode(x)),
        ("dict", Values::Int(x)) => Ok(dict::encode(x)),
        ("dict", Values::Float(x)) => Ok(dict::encode(&to_bits(x))),
        ("dict", Values::Str(x)) => Ok(dict::encode(x)),
        ("delta", Values::Int(x)) => Ok(delta::encode(x)),
        ("for", Values::Int(x)) => Ok(frame::encode(x)),
        ("bitpack", Values::Int(x)) => Ok(bitpack::encode(x)),
        ("alp", Values::Float(x)) => Ok(alp::encode(x)),
        ("fsst", Values::Str(x)) => Ok(fsst::encode(x)),
        _ => Err(format!("encoding {} does not apply to {} columns", name, v.kind())),
    }
}

pub fn decode(name: &str, kind: &str, bytes: &[u8]) -> Res<Values> {
    let mut r = Reader::new(bytes);
    let out = match (name, kind) {
        ("plain", _) => plain::decode(&mut r, kind)?,
        ("rle", "int") => Values::Int(rle::decode(&mut r)?),
        ("rle", "float") => Values::Float(from_bits(rle::decode(&mut r)?)),
        ("rle", "str") => Values::Str(rle::decode(&mut r)?),
        ("dict", "int") => Values::Int(dict::decode(&mut r)?),
        ("dict", "float") => Values::Float(from_bits(dict::decode(&mut r)?)),
        ("dict", "str") => Values::Str(dict::decode(&mut r)?),
        ("delta", "int") => Values::Int(delta::decode(&mut r)?),
        ("for", "int") => Values::Int(frame::decode(&mut r)?),
        ("bitpack", "int") => Values::Int(bitpack::decode(&mut r)?),
        ("alp", "float") => Values::Float(alp::decode(&mut r)?),
        ("fsst", "str") => Values::Str(fsst::decode(&mut r)?),
        _ => return Err(format!("encoding {} does not apply to {} columns", name, kind)),
    };
    if !r.done() {
        return Err("trailing bytes after decode".into());
    }
    Ok(out)
}

fn to_bits(x: &[f64]) -> Vec<u64> {
    x.iter().map(|f| f.to_bits()).collect()
}

fn from_bits(x: Vec<u64>) -> Vec<f64> {
    x.into_iter().map(f64::from_bits).collect()
}

pub trait Item: Clone + Eq + Hash {
    fn put(&self, out: &mut Vec<u8>);
    fn get(r: &mut Reader) -> Res<Self>;
}

impl Item for i64 {
    fn put(&self, out: &mut Vec<u8>) {
        out.extend_from_slice(&self.to_le_bytes());
    }
    fn get(r: &mut Reader) -> Res<Self> {
        r.u64().map(|u| u as i64)
    }
}

impl Item for u64 {
    fn put(&self, out: &mut Vec<u8>) {
        out.extend_from_slice(&self.to_le_bytes());
    }
    fn get(r: &mut Reader) -> Res<Self> {
        r.u64()
    }
}

impl Item for String {
    fn put(&self, out: &mut Vec<u8>) {
        put_varint(out, self.len() as u64);
        out.extend_from_slice(self.as_bytes());
    }
    fn get(r: &mut Reader) -> Res<Self> {
        let n = r.len()?;
        String::from_utf8(r.take(n)?.to_vec()).map_err(|e| e.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn check(v: Values) {
        for name in encodings(v.kind()) {
            let e = encode(name, &v).unwrap();
            let d = decode(name, v.kind(), &e.bytes).unwrap();
            assert!(v.same(&d), "{} lost data on {:?}", name, v);
        }
    }

    #[test]
    fn integers_survive_every_encoding_at_the_edges() {
        check(Values::Int(vec![]));
        check(Values::Int(vec![42]));
        check(Values::Int(vec![i64::MIN, i64::MAX, i64::MIN, 0, -1, i64::MAX]));
        check(Values::Int((0..5000).map(|i| (i * 7919) % 1000 - 500).collect()));
        check(Values::Int((0..3000).map(|i| i * 1_000_003).collect()));
        check(Values::Int(vec![7; 4097]));
    }

    #[test]
    fn floats_survive_bit_for_bit_including_nan_and_negative_zero() {
        check(Values::Float(vec![]));
        check(Values::Float(vec![f64::NAN, -0.0, 0.0, f64::INFINITY, f64::NEG_INFINITY, f64::MIN_POSITIVE / 3.0, 1e300, -1e-300]));
        check(Values::Float((0..5000).map(|i| (i as f64) / 100.0).collect()));
        check(Values::Float((0..3000).map(|i| (i as f64).sqrt()).collect()));
        check(Values::Float(vec![0.1 + 0.2, 1.0 / 3.0, 9007199254740993.0, 12.34, -12.34]));
    }

    #[test]
    fn strings_survive_every_encoding_including_unicode_and_empty() {
        check(Values::Str(vec![]));
        check(Values::Str(vec![String::new()]));
        check(Values::Str(vec!["".into(), "a".into(), "naïve café ☕ 日本".into(), "x".repeat(300), "line\nbreak\u{0}".into()]));
        check(Values::Str((0..4000).map(|i| format!("https://www.shop.com/p/{}?ref=mail", i % 97)).collect()));
    }

    #[test]
    fn decoding_garbage_fails_instead_of_inventing_values() {
        for name in encodings("int") {
            assert!(decode(name, "int", &[0xff, 0xff, 0xff]).is_err(), "{} accepted garbage", name);
        }
        assert!(decode("delta", "float", &[0]).is_err());
    }
}
