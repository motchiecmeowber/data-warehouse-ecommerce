"""Nhãn tiếng Việt cho các giá trị mã trong kho dữ liệu (danh mục, trạng thái, thanh toán, vùng)."""
import pandas as pd

CATEGORY = {
    "agro_industry_and_commerce": "Nông nghiệp và thương mại", "air_conditioning": "Điều hòa không khí",
    "art": "Nghệ thuật", "arts_and_craftmanship": "Thủ công mỹ nghệ", "audio": "Âm thanh", "auto": "Ô tô, xe máy",
    "baby": "Đồ cho bé", "bed_bath_table": "Chăn ga, phòng tắm, bàn ăn", "books_general_interest": "Sách phổ thông",
    "books_imported": "Sách nhập khẩu", "books_technical": "Sách kỹ thuật", "cds_dvds_musicals": "CD, DVD, nhạc kịch",
    "christmas_supplies": "Đồ trang trí Giáng sinh", "cine_photo": "Phim ảnh, nhiếp ảnh", "computers": "Máy tính",
    "computers_accessories": "Phụ kiện máy tính", "consoles_games": "Máy chơi game",
    "construction_tools_construction": "Dụng cụ xây dựng", "construction_tools_lights": "Đèn chiếu sáng xây dựng",
    "construction_tools_safety": "An toàn xây dựng", "cool_stuff": "Đồ độc đáo",
    "costruction_tools_garden": "Dụng cụ làm vườn (xây dựng)", "costruction_tools_tools": "Dụng cụ cầm tay",
    "diapers_and_hygiene": "Tã và vệ sinh", "drinks": "Đồ uống", "dvds_blu_ray": "DVD, Blu-ray",
    "electronics": "Đồ điện tử", "fashio_female_clothing": "Thời trang nữ", "fashion_bags_accessories": "Túi và phụ kiện",
    "fashion_childrens_clothes": "Quần áo trẻ em", "fashion_male_clothing": "Thời trang nam", "fashion_shoes": "Giày dép",
    "fashion_sport": "Thời trang thể thao", "fashion_underwear_beach": "Đồ lót, đồ đi biển",
    "fixed_telephony": "Điện thoại cố định", "flowers": "Hoa", "food": "Thực phẩm", "food_drink": "Thực phẩm và đồ uống",
    "furniture_bedroom": "Nội thất phòng ngủ", "furniture_decor": "Nội thất, trang trí",
    "furniture_living_room": "Nội thất phòng khách", "furniture_mattress_and_upholstery": "Nệm và bọc ghế",
    "garden_tools": "Dụng cụ làm vườn", "health_beauty": "Sức khỏe và làm đẹp", "home_appliances": "Đồ gia dụng",
    "home_appliances_2": "Đồ gia dụng (nhóm 2)", "home_comfort_2": "Tiện nghi gia đình (nhóm 2)",
    "home_confort": "Tiện nghi gia đình", "home_construction": "Xây dựng nhà ở", "housewares": "Đồ dùng gia đình",
    "industry_commerce_and_business": "Công nghiệp, thương mại",
    "kitchen_dining_laundry_garden_furniture": "Nội thất bếp, ăn, giặt, vườn", "la_cuisine": "Ẩm thực (La Cuisine)",
    "luggage_accessories": "Vali và phụ kiện", "market_place": "Chợ điện tử", "music": "Âm nhạc",
    "musical_instruments": "Nhạc cụ", "office_furniture": "Nội thất văn phòng", "party_supplies": "Đồ trang trí tiệc",
    "pc_gamer": "Máy tính chơi game", "perfumery": "Nước hoa", "pet_shop": "Thú cưng",
    "portable_kitchen_and_food_preparers": "Dụng cụ bếp di động", "security_and_services": "An ninh và dịch vụ",
    "signaling_and_security": "Báo hiệu và an ninh", "small_appliances": "Đồ điện gia dụng nhỏ",
    "small_appliances_home_oven_and_coffee": "Lò nướng, máy pha cà phê", "sports_leisure": "Thể thao, giải trí",
    "stationery": "Văn phòng phẩm", "tablets_printing_image": "Máy tính bảng, in ấn", "telephony": "Điện thoại",
    "toys": "Đồ chơi", "unknown": "Chưa phân loại", "watches_gifts": "Đồng hồ, quà tặng",
}
STATUS = {
    "delivered": "Đã giao", "shipped": "Đang vận chuyển", "canceled": "Đã hủy", "unavailable": "Hết hàng",
    "invoiced": "Đã xuất hóa đơn", "processing": "Đang xử lý", "created": "Mới tạo", "approved": "Đã duyệt",
}
PAYMENT = {
    "credit_card": "Thẻ tín dụng", "boleto": "Boleto (phiếu thanh toán)", "voucher": "Voucher",
    "debit_card": "Thẻ ghi nợ", "unknown": "Không rõ",
}
REGION = {
    "Norte": "Bắc (Norte)", "Nordeste": "Đông Bắc (Nordeste)", "Centro-Oeste": "Trung Tây (Centro-Oeste)",
    "Sudeste": "Đông Nam (Sudeste)", "Sul": "Nam (Sul)",
}
# cột trong view -> bảng nhãn
BY_COLUMN = {
    "category": CATEGORY, "order_status": STATUS, "payment_type": PAYMENT,
    "customer_region": REGION, "seller_region": REGION,
}


def vi(column: str, value) -> str:
    """Nhãn tiếng Việt của một giá trị trong cột `column`; không có trong bảng thì giữ nguyên."""
    if pd.isna(value):
        return "Tổng"
    mapping = BY_COLUMN.get(column, {})
    return mapping.get(value, value if isinstance(value, str) else str(value))


def localize(df: pd.DataFrame, *columns: str) -> pd.DataFrame:
    """Bản sao của df với các cột mã được đổi sang nhãn tiếng Việt."""
    out = df.copy()
    for col in columns:
        out[col] = out[col].map(lambda v, c=col: vi(c, v))
    return out
