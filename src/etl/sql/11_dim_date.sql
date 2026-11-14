-- dim_date: 1 dòng mỗi ngày, 2016-09-01 -> 2018-12-31; ngày lễ lấy từ staging.ref_brazil_holidays.

INSERT INTO dw.dim_date (
    date_key, full_date, "day", "month", month_name, "quarter", "year", year_month,
    day_of_week, day_name, is_weekend, is_holiday, holiday_name, is_black_friday
)
SELECT
    to_char(d, 'YYYYMMDD')::int,
    d,
    extract(day FROM d),
    extract(month FROM d),
    to_char(d, 'FMMonth'),
    extract(quarter FROM d),
    extract(year FROM d),
    to_char(d, 'YYYY-MM'),
    extract(isodow FROM d),                     -- 1 = thứ Hai ... 7 = Chủ nhật
    to_char(d, 'FMDay'),
    extract(isodow FROM d) IN (6, 7),
    h.holiday_date IS NOT NULL,
    h.holiday_name,
    -- Black Friday: thứ Sáu sau thứ Năm thứ tư của tháng 11 (luôn rơi vào ngày 23-29)
    extract(month FROM d) = 11 AND extract(isodow FROM d) = 5 AND extract(day FROM d) BETWEEN 23 AND 29
FROM generate_series(DATE '2016-09-01', DATE '2018-12-31', INTERVAL '1 day') AS g(ts)
CROSS JOIN LATERAL (SELECT g.ts::date AS d) AS x
LEFT JOIN staging.ref_brazil_holidays h ON h.holiday_date::date = x.d
ORDER BY d;