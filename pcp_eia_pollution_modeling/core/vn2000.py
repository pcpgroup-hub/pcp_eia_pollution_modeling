# -*- coding: utf-8 -*-
"""VN-2000 TM-3 (3-degree zone) central meridians by province (pure Python, no QGIS).

Source: Thong tu 973/2001/TT-TCDC (Tong cuc Dia chinh), Phu luc, Bang 4 (kinh tuyen truc theo tinh, thanh pho).
Province names are as written in 2001 (Ha Tay is now part of Ha Noi; further administrative mergers may apply):
pick the province whose area contains the project and confirm the zone against the current regulation.
Scale factor 0.9999, false easting 500000 m. EPSG codes are the ones QGIS/PROJ assigns to these zones.
"""

# (name, central meridian in decimal degrees)
PROVINCES = (
    ("Lai Châu", 103.0), ("Sơn La", 104.0), ("Kiên Giang", 104.5), ("Cà Mau", 104.5),
    ("Lào Cai", 104.75), ("Yên Bái", 104.75), ("Nghệ An", 104.75), ("Phú Thọ", 104.75), ("An Giang", 104.75),
    ("Thanh Hoá", 105.0), ("Vĩnh Phúc", 105.0), ("Hà Tây (cũ, nay thuộc Hà Nội)", 105.0), ("Đồng Tháp", 105.0),
    ("Cần Thơ", 105.0), ("Bạc Liêu", 105.0), ("Hà Nội", 105.0), ("Ninh Bình", 105.0), ("Hà Nam", 105.0),
    ("Hà Giang", 105.5), ("Hải Dương", 105.5), ("Hà Tĩnh", 105.5), ("Bắc Ninh", 105.5), ("Hưng Yên", 105.5),
    ("Thái Bình", 105.5), ("Nam Định", 105.5), ("Tây Ninh", 105.5), ("Vĩnh Long", 105.5), ("Sóc Trăng", 105.5),
    ("Trà Vinh", 105.5),
    ("Cao Bằng", 105.75), ("Long An", 105.75), ("Tiền Giang", 105.75), ("Bến Tre", 105.75), ("Hải Phòng", 105.75),
    ("TP. Hồ Chí Minh", 105.75), ("Bình Dương", 105.75),
    ("Tuyên Quang", 106.0), ("Hoà Bình", 106.0), ("Quảng Bình", 106.0),
    ("Quảng Trị", 106.25), ("Bình Phước", 106.25),
    ("Bắc Kạn", 106.5), ("Thái Nguyên", 106.5),
    ("Bắc Giang", 107.0), ("Thừa Thiên Huế", 107.0),
    ("Lạng Sơn", 107.25), ("Kon Tum", 107.5),
    ("Quảng Ninh", 107.75), ("Đồng Nai", 107.75), ("Bà Rịa – Vũng Tàu", 107.75), ("Quảng Nam", 107.75),
    ("Lâm Đồng", 107.75), ("Đà Nẵng", 107.75),
    ("Quảng Ngãi", 108.0),
    ("Ninh Thuận", 108.25), ("Khánh Hoà", 108.25), ("Bình Định", 108.25),
    ("Đắk Lắk", 108.5), ("Phú Yên", 108.5), ("Gia Lai", 108.5), ("Bình Thuận", 108.5),
)

K0 = 0.9999
TOWGS84 = "-191.90441429,-39.30318279,-111.45032835,0.00928836,-0.01975479,0.00427372,0.252906278"

# central meridian -> EPSG code of VN-2000 / TM-3 zone
EPSG_BY_MERIDIAN = {
    103.0: 9205, 104.0: 9206, 104.5: 9207, 104.75: 9208, 105.0: 5897, 105.5: 9209, 105.75: 9210,
    106.0: 9211, 106.25: 9212, 106.5: 9213, 107.0: 9214, 107.25: 9215, 107.5: 9216, 107.75: 5899,
    108.0: 5898, 108.25: 9217, 108.5: 9218,
}


def province_names():
    return [n for n, _ in PROVINCES]


def central_meridian(name):
    for n, m in PROVINCES:
        if n == name:
            return m
    raise KeyError("Unknown province: %s" % name)


def epsg_for(name):
    return EPSG_BY_MERIDIAN[central_meridian(name)]


def proj_string(meridian):
    """PROJ string of the TM-3 zone, usable when the EPSG code is not in the user's database."""
    return ("+proj=tmerc +lat_0=0 +lon_0=%s +k=%s +x_0=500000 +y_0=0 +ellps=WGS84 +towgs84=%s +units=m +no_defs"
            % (meridian, K0, TOWGS84))


def dms_label(meridian):
    d = int(meridian)
    m = int(round((meridian - d) * 60))
    return "%d°%02d′" % (d, m)
