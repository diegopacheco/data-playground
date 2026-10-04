pub type Res<T> = Result<T, String>;

const MAX_COUNT: usize = 1 << 26;

pub struct Reader<'a> {
    buf: &'a [u8],
    pos: usize,
}

impl<'a> Reader<'a> {
    pub fn new(buf: &'a [u8]) -> Self {
        Reader { buf, pos: 0 }
    }

    pub fn take(&mut self, n: usize) -> Res<&'a [u8]> {
        let end = self.pos.checked_add(n).filter(|e| *e <= self.buf.len()).ok_or("truncated input")?;
        let out = &self.buf[self.pos..end];
        self.pos = end;
        Ok(out)
    }

    pub fn u8(&mut self) -> Res<u8> {
        Ok(self.take(1)?[0])
    }

    pub fn u16(&mut self) -> Res<u16> {
        Ok(u16::from_le_bytes(self.take(2)?.try_into().unwrap()))
    }

    pub fn u64(&mut self) -> Res<u64> {
        Ok(u64::from_le_bytes(self.take(8)?.try_into().unwrap()))
    }

    pub fn varint(&mut self) -> Res<u64> {
        let mut out = 0u64;
        let mut shift = 0;
        loop {
            let b = self.u8()?;
            if shift > 63 {
                return Err("varint too long".into());
            }
            out |= ((b & 0x7f) as u64) << shift;
            if b & 0x80 == 0 {
                return Ok(out);
            }
            shift += 7;
        }
    }

    pub fn ivarint(&mut self) -> Res<i64> {
        Ok(unzigzag(self.varint()?))
    }

    pub fn len(&mut self) -> Res<usize> {
        let n = self.varint()? as usize;
        if n > MAX_COUNT {
            return Err("length out of range".into());
        }
        Ok(n)
    }

    pub fn done(&self) -> bool {
        self.pos == self.buf.len()
    }
}

pub fn put_varint(out: &mut Vec<u8>, mut v: u64) {
    while v >= 0x80 {
        out.push((v as u8) | 0x80);
        v >>= 7;
    }
    out.push(v as u8);
}

pub fn put_ivarint(out: &mut Vec<u8>, v: i64) {
    put_varint(out, zigzag(v));
}

pub fn zigzag(v: i64) -> u64 {
    ((v << 1) ^ (v >> 63)) as u64
}

pub fn unzigzag(v: u64) -> i64 {
    ((v >> 1) as i64) ^ -((v & 1) as i64)
}

pub fn width(max: u64) -> u32 {
    64 - max.leading_zeros()
}

pub fn pack(vals: &[u64], w: u32, out: &mut Vec<u8>) {
    if w == 0 {
        return;
    }
    let mut acc: u128 = 0;
    let mut n = 0u32;
    for &v in vals {
        acc |= (v as u128) << n;
        n += w;
        while n >= 8 {
            out.push(acc as u8);
            acc >>= 8;
            n -= 8;
        }
    }
    if n > 0 {
        out.push(acc as u8);
    }
}

pub fn unpack(r: &mut Reader, count: usize, w: u32) -> Res<Vec<u64>> {
    if w > 64 {
        return Err("bit width over 64".into());
    }
    let bytes = r.take((count * w as usize).div_ceil(8))?;
    if w == 0 {
        return Ok(vec![0; count]);
    }
    let mask = if w == 64 { u64::MAX } else { (1u64 << w) - 1 };
    let mut out = Vec::with_capacity(count);
    let mut acc: u128 = 0;
    let mut n = 0u32;
    let mut i = 0;
    for _ in 0..count {
        while n < w {
            acc |= (bytes[i] as u128) << n;
            i += 1;
            n += 8;
        }
        out.push(acc as u64 & mask);
        acc >>= w;
        n -= w;
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pack_round_trips_every_width_including_64() {
        for w in 0..=64u32 {
            let mask = if w == 64 { u64::MAX } else { (1u64 << w) - 1 };
            let vals: Vec<u64> = (0..77u64).map(|i| i.wrapping_mul(0x9E3779B97F4A7C15) & mask).collect();
            let mut out = Vec::new();
            pack(&vals, w, &mut out);
            assert_eq!(out.len(), (77 * w as usize).div_ceil(8));
            assert_eq!(unpack(&mut Reader::new(&out), 77, w).unwrap(), vals);
        }
    }

    #[test]
    fn zigzag_keeps_small_magnitudes_small() {
        for v in [0i64, -1, 1, -2, i64::MIN, i64::MAX] {
            assert_eq!(unzigzag(zigzag(v)), v);
        }
        assert_eq!(zigzag(-1), 1);
        assert_eq!(zigzag(1), 2);
    }
}
