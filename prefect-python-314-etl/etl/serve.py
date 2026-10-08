from flow import revenue_etl

if __name__ == "__main__":
    revenue_etl.serve(name="hourly", cron="0 * * * *", tags=["i37"])
