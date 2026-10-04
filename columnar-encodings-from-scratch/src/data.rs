use crate::codec::Values;

pub struct Column {
    pub name: &'static str,
    pub about: &'static str,
    pub values: Values,
}

struct Rng(u64);

impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 >> 12;
        self.0 ^= self.0 << 25;
        self.0 ^= self.0 >> 27;
        self.0.wrapping_mul(0x2545F4914F6CDD1D)
    }

    fn below(&mut self, n: u64) -> u64 {
        self.next() % n
    }

    fn pick<'a>(&mut self, xs: &[&'a str]) -> &'a str {
        xs[self.below(xs.len() as u64) as usize]
    }
}

const COUNTRIES: [(&str, u64); 12] = [
    ("US", 30), ("BR", 14), ("DE", 10), ("IN", 9), ("GB", 8), ("FR", 7), ("JP", 6), ("CA", 5), ("MX", 4), ("AU", 3), ("ES", 2), ("PT", 2),
];
const SHOPS: [&str; 10] = ["acme", "bluebird", "cornerstore", "dailydeals", "evergreen", "fastcart", "goodbuy", "homegoods", "idealhub", "jetmarket"];
const SECTIONS: [&str; 8] = ["products", "category", "checkout", "account", "search", "blog", "offers", "support"];
const SLUGS: [&str; 12] = ["running-shoes", "coffee-maker", "wireless-headphones", "office-chair", "yoga-mat", "water-bottle", "desk-lamp", "backpack", "sunglasses", "phone-case", "garden-hose", "air-fryer"];
const SOURCES: [&str; 5] = ["newsletter", "google", "facebook", "partner", "direct"];
const FIRST: [&str; 16] = ["ana", "bruno", "carla", "diego", "elena", "felipe", "gabriela", "hugo", "isabel", "joao", "karen", "lucas", "marta", "nicolas", "olivia", "pedro"];
const LAST: [&str; 16] = ["silva", "santos", "oliveira", "souza", "lima", "pereira", "costa", "rodrigues", "almeida", "nunes", "gomes", "martins", "rocha", "ribeiro", "carvalho", "teixeira"];
const MAIL: [&str; 5] = ["gmail.com", "yahoo.com", "outlook.com", "proton.me", "icloud.com"];

pub fn generate(rows: usize) -> Vec<Column> {
    let mut rng = Rng(2026);
    let mut order_id = 1_000_000i64;
    let sorted: Vec<i64> = (0..rows).map(|_| { order_id += 1 + rng.below(3) as i64; order_id }).collect();
    let mut ts = 1_767_225_600_000_000i64;
    let times: Vec<i64> = (0..rows).map(|_| { ts += rng.below(2_000_000) as i64; ts }).collect();
    let days: Vec<i64> = (0..rows).map(|i| 20260101 + (i * 30 / rows.max(1)) as i64).collect();
    let weight: u64 = COUNTRIES.iter().map(|c| c.1).sum();
    let countries: Vec<String> = (0..rows).map(|_| {
        let mut w = rng.below(weight);
        COUNTRIES.iter().find(|c| { let hit = w < c.1; w = w.saturating_sub(c.1); hit }).unwrap().0.to_string()
    }).collect();
    let links: Vec<String> = (0..rows).map(|_| {
        if rng.below(2) == 0 {
            format!("https://www.{}.com/{}/{}-{}?utm_source={}", rng.pick(&SHOPS), rng.pick(&SECTIONS), rng.pick(&SLUGS), rng.below(100_000), rng.pick(&SOURCES))
        } else {
            format!("{}.{}{}@{}", rng.pick(&FIRST), rng.pick(&LAST), rng.below(1000), rng.pick(&MAIL))
        }
    }).collect();
    let prices: Vec<f64> = (0..rows).map(|_| (99 + rng.below(99_900)) as f64 / 100.0).collect();
    let random: Vec<i64> = (0..rows).map(|_| rng.below(1_000_000_000) as i64).collect();
    vec![
        Column { name: "sorted_ints", about: "order_id: ascending ids with gaps of 1-3", values: Values::Int(sorted) },
        Column { name: "timestamps", about: "event_time: microseconds since epoch, sorted, 0-2 s apart", values: Values::Int(times) },
        Column { name: "day_keys", about: "event_day: yyyymmdd for 30 days, clustered like a table sorted by day", values: Values::Int(days) },
        Column { name: "low_card_strings", about: "country: 12 ISO codes, skewed, random order", values: Values::Str(countries) },
        Column { name: "urls_emails", about: "link: shop URLs with utm tags mixed with email addresses", values: Values::Str(links) },
        Column { name: "prices", about: "price: doubles with 2 decimals between 0.99 and 999.98", values: Values::Float(prices) },
        Column { name: "random_ints", about: "random_id: uniform integers in [0, 1e9)", values: Values::Int(random) },
    ]
}
