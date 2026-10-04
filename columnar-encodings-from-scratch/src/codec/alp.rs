use super::frame::{get_block, put_block};
use super::Encoded;
use crate::bits::{put_varint, width, Reader, Res};
use std::collections::BTreeMap;

const VECTOR: usize = 1024;
const CANDIDATES: usize = 5;
const F10: [f64; 19] = [1e0, 1e1, 1e2, 1e3, 1e4, 1e5, 1e6, 1e7, 1e8, 1e9, 1e10, 1e11, 1e12, 1e13, 1e14, 1e15, 1e16, 1e17, 1e18];
const IF10: [f64; 19] = [1e0, 1e-1, 1e-2, 1e-3, 1e-4, 1e-5, 1e-6, 1e-7, 1e-8, 1e-9, 1e-10, 1e-11, 1e-12, 1e-13, 1e-14, 1e-15, 1e-16, 1e-17, 1e-18];

fn to_int(v: f64, e: usize, f: usize) -> Option<i64> {
    let x = (v * F10[e] * IF10[f]).round();
    if !x.is_finite() || x.abs() > 4.5e18 {
        return None;
    }
    let i = x as i64;
    (from_int(i, e, f).to_bits() == v.to_bits()).then_some(i)
}

fn from_int(i: i64, e: usize, f: usize) -> f64 {
    i as f64 * F10[f] * IF10[e]
}

fn cost(x: &[f64], e: usize, f: usize) -> u64 {
    let (mut lo, mut hi, mut ok, mut bad) = (i64::MAX, i64::MIN, 0u64, 0u64);
    for v in x {
        match to_int(*v, e, f) {
            Some(i) => {
                lo = lo.min(i);
                hi = hi.max(i);
                ok += 1;
            }
            None => bad += 1,
        }
    }
    let w = if ok == 0 { 0 } else { width((hi as i128 - lo as i128) as u64) as u64 };
    w * ok + bad * 80
}

fn best_combos(x: &[f64]) -> Vec<(usize, usize)> {
    let step = (x.len() / VECTOR).max(1);
    let sample: Vec<f64> = x.iter().step_by(step).copied().collect();
    let mut all: Vec<(u64, usize, usize)> = (0..19).flat_map(|e| (0..=e).map(move |f| (e, f))).map(|(e, f)| (cost(&sample, e, f), e, f)).collect();
    all.sort();
    all.into_iter().take(CANDIDATES).map(|(_, e, f)| (e, f)).collect()
}

pub fn encode(x: &[f64]) -> Encoded {
    let combos = best_combos(x);
    let mut out = Vec::new();
    put_varint(&mut out, x.len() as u64);
    let mut used: BTreeMap<(usize, usize), usize> = BTreeMap::new();
    let mut exceptions = 0usize;
    for vec in x.chunks(VECTOR) {
        let (e, f) = *combos.iter().min_by_key(|(e, f)| cost(vec, *e, *f)).unwrap();
        *used.entry((e, f)).or_default() += 1;
        let ints: Vec<Option<i64>> = vec.iter().map(|v| to_int(*v, e, f)).collect();
        let fill = ints.iter().flatten().next().copied().unwrap_or(0);
        let exc: Vec<(usize, f64)> = ints.iter().zip(vec).enumerate().filter(|(_, (i, _))| i.is_none()).map(|(p, (_, v))| (p, *v)).collect();
        exceptions += exc.len();
        out.push(e as u8);
        out.push(f as u8);
        put_varint(&mut out, exc.len() as u64);
        put_block(&ints.iter().map(|i| i.unwrap_or(fill)).collect::<Vec<_>>(), &mut out);
        for (p, v) in exc {
            out.extend_from_slice(&(p as u16).to_le_bytes());
            out.extend_from_slice(&v.to_le_bytes());
        }
    }
    let pairs: Vec<String> = used.iter().map(|((e, f), n)| format!("e={} f={} in {} vectors", e, f, n)).collect();
    let pct = if x.is_empty() { 0.0 } else { exceptions as f64 * 100.0 / x.len() as f64 };
    Encoded {
        bytes: out,
        detail: format!("decimal exponents chosen: {}; {} exceptions ({:.3}%) stored as raw doubles", pairs.join(", "), exceptions, pct),
    }
}

pub fn decode(r: &mut Reader) -> Res<Vec<f64>> {
    let n = r.len()?;
    let mut out = Vec::with_capacity(n);
    let mut ints = Vec::with_capacity(VECTOR);
    while out.len() < n {
        let count = VECTOR.min(n - out.len());
        let (e, f) = (r.u8()? as usize, r.u8()? as usize);
        if e > 18 || f > e {
            return Err("bad alp exponent".into());
        }
        let exc = r.varint()? as usize;
        ints.clear();
        get_block(r, count, &mut ints)?;
        let start = out.len();
        out.extend(ints.iter().map(|i| from_int(*i, e, f)));
        for _ in 0..exc {
            let p = r.u16()? as usize;
            let v = f64::from_bits(r.u64()?);
            *out.get_mut(start + p).filter(|_| p < count).ok_or("exception position out of range")? = v;
        }
    }
    Ok(out)
}
