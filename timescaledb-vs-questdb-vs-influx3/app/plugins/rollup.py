def process_request(influxdb3_local, query_parameters, request_headers, request_body, args=None):
    start = int(query_parameters["start"])
    stop = int(query_parameters["stop"])
    rows = influxdb3_local.query(f"""
        SELECT device, date_part('epoch', date_bin(INTERVAL '1 hour', time))::BIGINT AS bucket,
               avg(temperature) AS avg_t, min(temperature) AS min_t, max(temperature) AS max_t
        FROM readings WHERE time >= to_timestamp_seconds({start}) AND time < to_timestamp_seconds({stop})
        GROUP BY 1, 2
    """)
    for r in rows:
        line = LineBuilder("readings_1h")
        line.tag("device", r["device"])
        line.float64_field("avg_t", r["avg_t"])
        line.float64_field("min_t", r["min_t"])
        line.float64_field("max_t", r["max_t"])
        line.time_ns(r["bucket"] * 1000000000)
        influxdb3_local.write(line)
    return {"rows": len(rows)}
