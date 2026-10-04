use super::Encoded;
use crate::bits::{put_varint, Reader, Res};
use std::collections::HashMap;

const ESCAPE: u8 = 255;
const MAX_SYMBOLS: usize = 255;
const SAMPLE_BYTES: usize = 1 << 16;
const GENERATIONS: usize = 5;
const CODES: usize = 256 + MAX_SYMBOLS;

#[derive(Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
struct Symbol {
    val: u64,
    len: u8,
}

impl Symbol {
    fn bytes(&self) -> Vec<u8> {
        self.val.to_le_bytes()[..self.len as usize].to_vec()
    }
}

struct Table {
    symbols: Vec<Symbol>,
    by_first: Vec<Vec<u8>>,
}

fn mask(len: u8) -> u64 {
    if len >= 8 { u64::MAX } else { (1u64 << (8 * len as u32)) - 1 }
}

impl Table {
    fn new(symbols: Vec<Symbol>) -> Table {
        let mut by_first = vec![Vec::new(); 256];
        for (code, s) in symbols.iter().enumerate() {
            by_first[(s.val & 0xff) as usize].push(code as u8);
        }
        for list in by_first.iter_mut() {
            list.sort_by_key(|c| std::cmp::Reverse(symbols[*c as usize].len));
        }
        Table { symbols, by_first }
    }

    fn find(&self, s: &[u8], p: usize) -> Option<(u8, usize)> {
        let rest = &s[p..];
        let mut word = 0u64;
        for (k, b) in rest.iter().take(8).enumerate() {
            word |= (*b as u64) << (8 * k);
        }
        self.by_first[rest[0] as usize]
            .iter()
            .map(|c| (*c, self.symbols[*c as usize]))
            .find(|(_, sym)| sym.len as usize <= rest.len() && word & mask(sym.len) == sym.val)
            .map(|(c, sym)| (c, sym.len as usize))
    }

    fn compress(&self, s: &[u8], out: &mut Vec<u8>) {
        let mut p = 0;
        while p < s.len() {
            match self.find(s, p) {
                Some((c, l)) => {
                    out.push(c);
                    p += l;
                }
                None => {
                    out.push(ESCAPE);
                    out.push(s[p]);
                    p += 1;
                }
            }
        }
    }

    fn pseudo(&self, code: usize) -> Symbol {
        if code < 256 { Symbol { val: code as u64, len: 1 } } else { self.symbols[code - 256] }
    }
}

fn sample(x: &[String]) -> Vec<&[u8]> {
    let total: usize = x.iter().map(|s| s.len()).sum();
    let step = (total / SAMPLE_BYTES).max(1);
    x.iter().step_by(step).map(|s| s.as_bytes()).filter(|s| !s.is_empty()).collect()
}

fn train(x: &[String]) -> Table {
    let sample = sample(x);
    let mut table = Table::new(Vec::new());
    for _ in 0..GENERATIONS {
        let mut single = vec![0u64; CODES];
        let mut pair = vec![0u64; CODES * CODES];
        for s in &sample {
            let mut p = 0;
            let mut prev: Option<usize> = None;
            while p < s.len() {
                let (code, len) = match table.find(s, p) {
                    Some((c, l)) => (256 + c as usize, l),
                    None => (s[p] as usize, 1),
                };
                single[code] += 1;
                if let Some(pc) = prev {
                    pair[pc * CODES + code] += 1;
                }
                prev = Some(code);
                p += len;
            }
        }
        let mut gain: HashMap<Symbol, u64> = HashMap::new();
        for a in (0..CODES).filter(|a| single[*a] > 0) {
            let sa = table.pseudo(a);
            *gain.entry(sa).or_default() += single[a] * sa.len as u64;
            for b in (0..CODES).filter(|b| pair[a * CODES + b] > 0) {
                let sb = table.pseudo(b);
                if sa.len + sb.len <= 8 {
                    let joined = Symbol { val: sa.val | (sb.val << (8 * sa.len as u32)), len: sa.len + sb.len };
                    *gain.entry(joined).or_default() += pair[a * CODES + b] * joined.len as u64;
                }
            }
        }
        let mut ranked: Vec<(u64, Symbol)> = gain.into_iter().map(|(s, g)| (g, s)).collect();
        ranked.sort_by(|a, b| b.cmp(a));
        table = Table::new(ranked.into_iter().take(MAX_SYMBOLS).map(|(_, s)| s).collect());
    }
    table
}

pub fn encode(x: &[String]) -> Encoded {
    let table = train(x);
    let mut out = Vec::new();
    put_varint(&mut out, x.len() as u64);
    out.push(table.symbols.len() as u8);
    for s in &table.symbols {
        out.push(s.len);
        out.extend_from_slice(&s.bytes());
    }
    let header = out.len();
    let mut buf = Vec::new();
    for s in x {
        buf.clear();
        table.compress(s.as_bytes(), &mut buf);
        put_varint(&mut out, buf.len() as u64);
        out.extend_from_slice(&buf);
    }
    let mut longest: Vec<&Symbol> = table.symbols.iter().collect();
    longest.sort_by_key(|s| std::cmp::Reverse(s.len));
    let shown: Vec<String> = longest.iter().take(16).map(|s| format!("{:?}", String::from_utf8_lossy(&s.bytes()))).collect();
    Encoded {
        bytes: out,
        detail: format!("{} symbols of 1-8 bytes in a {} byte table, longest: {}", table.symbols.len(), header, shown.join(" ")),
    }
}

pub fn decode(r: &mut Reader) -> Res<Vec<String>> {
    let n = r.len()?;
    let k = r.u8()? as usize;
    let mut symbols = Vec::with_capacity(k);
    for _ in 0..k {
        let len = r.u8()? as usize;
        if len == 0 || len > 8 {
            return Err("bad symbol length".into());
        }
        symbols.push(r.take(len)?);
    }
    let mut out = Vec::with_capacity(n);
    for _ in 0..n {
        let len = r.len()?;
        let codes = r.take(len)?;
        let mut s = Vec::with_capacity(len * 3);
        let mut i = 0;
        while i < codes.len() {
            let c = codes[i];
            if c == ESCAPE {
                s.push(*codes.get(i + 1).ok_or("escape at end of string")?);
                i += 2;
            } else {
                s.extend_from_slice(symbols.get(c as usize).ok_or("unknown symbol code")?);
                i += 1;
            }
        }
        out.push(String::from_utf8(s).map_err(|e| e.to_string())?);
    }
    Ok(out)
}
