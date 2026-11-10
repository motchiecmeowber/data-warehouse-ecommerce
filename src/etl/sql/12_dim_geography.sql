-- dim_geography: 1 dòng mỗi mã bưu điện.
-- Nguồn chính: geolocation (R15, R16, R29-R32). Mã chỉ có ở customers/sellers: R18, R34, R35.
-- Khung tọa độ Brazil (R29) đọc từ configs/etl.yaml (brazil_bbox), do Python truyền vào.

INSERT INTO dw.dim_geography (
    zip_code_prefix, city, state_code, state_name, region, latitude, longitude, has_coordinates
)
WITH bbox AS (
    SELECT
        current_setting('etl.lat_min')::numeric AS lat_min,
        current_setting('etl.lat_max')::numeric AS lat_max,
        current_setting('etl.lng_min')::numeric AS lng_min,
        current_setting('etl.lng_max')::numeric AS lng_max
),
geo AS (
    -- R15: bỏ dòng trùng hoàn toàn; R02: bù 0; R30: bỏ dấu, viết thường, cắt khoảng trắng
    SELECT
        lpad(zip, 5, '0')                       AS zip,
        lat::numeric                            AS lat,
        lng::numeric                            AS lng,
        lower(trim(unaccent(city)))             AS city,
        upper(trim(state))                      AS state
    FROM (
        SELECT DISTINCT
            geolocation_zip_code_prefix AS zip, geolocation_lat AS lat, geolocation_lng AS lng,
            geolocation_city AS city, geolocation_state AS state
        FROM staging.geolocation
    ) AS d
),
geo_by_zip AS (
    SELECT
        zip,
        mode() WITHIN GROUP (ORDER BY city)     AS city,    -- R31
        mode() WITHIN GROUP (ORDER BY state)    AS state,   -- R32
        -- R16: trung vị, chỉ tính trên tọa độ nằm trong khung Brazil (R29)
        percentile_cont(0.5) WITHIN GROUP (ORDER BY lat)
            FILTER (WHERE lat BETWEEN b.lat_min AND b.lat_max AND lng BETWEEN b.lng_min AND b.lng_max) AS lat,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY lng)
            FILTER (WHERE lat BETWEEN b.lat_min AND b.lat_max AND lng BETWEEN b.lng_min AND b.lng_max) AS lng
    FROM geo
    CROSS JOIN bbox b
    GROUP BY zip
),
other AS (
    -- R18: mã không có trong geolocation lấy thành phố, bang từ customers và sellers
    SELECT
        lpad(customer_zip_code_prefix, 5, '0')  AS zip,
        lower(trim(unaccent(customer_city)))    AS city,
        upper(trim(customer_state))             AS state
    FROM staging.customers
    UNION ALL
    SELECT
        lpad(s.seller_zip_code_prefix, 5, '0'),
        CASE WHEN c.city ~ '^[0-9]+$' THEN 'unknown' ELSE c.city END,   -- R34: toàn số -> unknown
        upper(trim(s.seller_state))                                     -- R35
    FROM staging.sellers s
    -- R34: cắt phần sau dấu / hoặc \, rồi áp R30
    CROSS JOIN LATERAL (
        SELECT lower(trim(unaccent(split_part(replace(s.seller_city, '\', '/'), '/', 1)))) AS city
    ) AS c
),
other_by_zip AS (
    SELECT
        zip,
        mode() WITHIN GROUP (ORDER BY city)     AS city,
        mode() WITHIN GROUP (ORDER BY state)    AS state
    FROM other
    WHERE zip NOT IN (SELECT zip FROM geo_by_zip)
    GROUP BY zip
),
all_zips AS (
    SELECT zip, city, state, lat, lng FROM geo_by_zip
    UNION ALL
    SELECT zip, city, state, NULL, NULL FROM other_by_zip
)
SELECT
    z.zip,
    z.city,
    z.state,
    s.state_name,
    s.region,
    round(z.lat::numeric, 6),
    round(z.lng::numeric, 6),
    z.lat IS NOT NULL AND z.lng IS NOT NULL
FROM all_zips z
LEFT JOIN staging.ref_brazil_states s ON s.state_code = z.state
ORDER BY z.zip;