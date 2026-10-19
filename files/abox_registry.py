# -*- coding: utf-8 -*-
"""
abox_registry.py - Nạp 20_di_san_verify.csv + 20_di_san_occurrence_2023_2025.csv vào ABox.

Nguyên tắc:
- CSV là nguồn chứng cứ: số/ngày QĐ, URL nguồn, văn bản gốc (time_rule, occ_*, admin_after_2025, notes) được đưa
  nguyên văn vào ich:source / rdfs:comment. Các cột free-text KHÔNG được parse tự động.
- Trường cấu trúc (hệ lịch, cửa sổ ngày, ngày âm của occurrence, class, cue) nằm ở bảng CURATED bên dưới,
  viết tay từ nội dung CSV + Khung thực thể. Mọi giá trị suy ra (không có nguyên văn trong CSV) ghi rõ trong comment.
- verificationStatus = "verified" chỉ khi CSV verify_level bắt đầu bằng "Cao" VÀ trường liên quan không có [chưa verify].
"""
import csv
import re
from pathlib import Path

from rdflib import Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

ICH = None   # gán trong build() từ namespace của gen_ich_owl
EX = None

DSVH_LIST = "https://dsvh.gov.vn/danh-muc-di-san-van-hoa-phi-vat-the-quoc-gia-1789"
NQ202_NOTE = "Sáp nhập tỉnh theo NQ 202/2025/QH15 (validTo/validFrom theo quy ước đã dùng trong ABox; mốc vận hành [chưa verify])."

# --------------------------------------------------------------------------
# Không gian: vùng tỉnh cũ (trước 6/2025) nằm trong vùng tỉnh mới
# --------------------------------------------------------------------------
# key: (class, nhãn, nằm trong)
PLACES = {
    "Place_DBSCL": ("Place", "Vùng Đồng bằng sông Cửu Long", "Place_NamBo"),
    "Place_NamBo": ("Place", "Vùng Nam Bộ", None),
    "Place_CanThoNewArea": (None, None, "Place_DBSCL"),          # đã có trong gen_ich_owl
    "Place_VinhLongNewArea": ("Place", "Vùng tỉnh Vĩnh Long (sau sáp nhập)", "Place_DBSCL"),
    "Place_AnGiangNewArea": ("Place", "Vùng tỉnh An Giang (sau sáp nhập)", "Place_DBSCL"),
    "Place_CaMauNewArea": ("Place", "Vùng tỉnh Cà Mau (sau sáp nhập)", "Place_DBSCL"),
    "Place_CanThoOldArea": ("Place", "Vùng TP Cần Thơ (trước sáp nhập)", "Place_CanThoNewArea"),
    "Place_SocTrangArea": (None, None, None),                     # đã có, đã nằm trong CanThoNewArea
    "Place_TraVinhArea": ("Place", "Vùng tỉnh Trà Vinh (cũ)", "Place_VinhLongNewArea"),
    "Place_AnGiangOldArea": ("Place", "Vùng tỉnh An Giang (cũ)", "Place_AnGiangNewArea"),
    "Place_KienGiangArea": ("Place", "Vùng tỉnh Kiên Giang (cũ)", "Place_AnGiangNewArea"),
    "Place_CaMauOldArea": ("Place", "Vùng tỉnh Cà Mau (cũ)", "Place_CaMauNewArea"),
    # địa điểm cụ thể (venue_specific trong CSV)
    "DinhBinhThuy": ("CulturalSpace", "Đình Bình Thủy", "Place_CanThoOldArea"),
    "ChuaKhleang": ("CulturalSpace", "Chùa Khleang", "Place_SocTrangArea"),
    "AoBaOm": ("CulturalSpace", "Khu di tích danh lam Ao Bà Om", "Place_TraVinhArea"),
    "SongLongBinh": ("NaturalFeature", "Sông Long Bình", "Place_TraVinhArea"),
    "SanDuaBoTaPa": ("Place", "Sân đua bò Tà Pạ – Soài Chek (Tri Tôn)", "Place_AnGiangOldArea"),
    "SanDuaBoVinhTrung": ("Place", "Sân đua bò xã Vĩnh Trung (Tịnh Biên)", "Place_AnGiangOldArea"),
    "LangOngNamHaiTranDe": ("CulturalSpace", "Lăng Ông Nam Hải (Trần Đề)", "Place_SocTrangArea"),
    "LangOngSongDoc": ("CulturalSpace", "Lăng Ông Nam Hải Đại Tướng quân (Sông Đốc)", "Place_CaMauOldArea"),
    "MieuBaChuaXuNuiSam": ("CulturalSpace", "Miếu Bà Chúa Xứ núi Sam", "Place_AnGiangOldArea"),
    "DinhThanNguyenTrungTruc": ("CulturalSpace", "Đình thần Nguyễn Trung Trực (Rạch Giá)", "Place_KienGiangArea"),
    "MieuBaChuaXuMyLong": ("CulturalSpace", "Miếu Bà Chúa Xứ Mỹ Long", "Place_TraVinhArea"),
    "TrungTamChroiRumChek": ("CulturalSpace", "Trung tâm hành lễ Chrôi Rum Chếk (Vĩnh Châu)", "Place_SocTrangArea"),
}

# AdminUnit cấp tỉnh: (nhãn, coversPlace, trước/sau 2025, succeededBy)
ADMINS = {
    "Admin_SocTrang_pre2025": (None, None, "pre", None),          # đã có
    "Admin_TPCanTho_2025": (None, None, "post", None),            # đã có
    "Admin_TPCanTho_pre2025": ("Thành phố Cần Thơ (trước sáp nhập)", "Place_CanThoOldArea", "pre", "Admin_TPCanTho_2025"),
    "Admin_TraVinh_pre2025": ("Tỉnh Trà Vinh", "Place_TraVinhArea", "pre", "Admin_VinhLong_2025"),
    "Admin_AnGiang_pre2025": ("Tỉnh An Giang (trước sáp nhập)", "Place_AnGiangOldArea", "pre", "Admin_AnGiang_2025"),
    "Admin_KienGiang_pre2025": ("Tỉnh Kiên Giang", "Place_KienGiangArea", "pre", "Admin_AnGiang_2025"),
    "Admin_CaMau_pre2025": ("Tỉnh Cà Mau (trước sáp nhập)", "Place_CaMauOldArea", "pre", "Admin_CaMau_2025"),
    "Admin_VinhLong_2025": ("Tỉnh Vĩnh Long (sau sáp nhập)", "Place_VinhLongNewArea", "post", None),
    "Admin_AnGiang_2025": ("Tỉnh An Giang (sau sáp nhập)", "Place_AnGiangNewArea", "post", None),
    "Admin_CaMau_2025": ("Tỉnh Cà Mau (sau sáp nhập)", "Place_CaMauNewArea", "post", None),
}

# --------------------------------------------------------------------------
# Từ vựng bổ sung (type-level). Nguồn: Khung thực thể (ví dụ) hoặc cột notes/venue của CSV -> unverified.
# --------------------------------------------------------------------------
# (iri, class, nhãn, cueKind | None)
VOCAB = [
    ("DuaBo", "SocialPractice", "Đua bò", "activity"),
    ("LeNghinhThanNamHai", "Ritual", "Lễ Nghinh Thần Nam Hải", "activity"),
    ("LeTeThanNong", "Ritual", "Lễ tế Thần Nông", "activity"),
    ("TongTau", "Ritual", "Lễ tống tàu", "activity"),
    ("RuocTuongBa", "Ritual", "Rước tượng Bà", "activity"),
    ("HatDuKe", "Performance", "Hát Dù Kê", "activity"),
    ("MuaRoBam", "Performance", "Múa Rô-băm", "activity"),
    ("DienTauNguAm", "Performance", "Diễn tấu nhạc Ngũ âm", "activity"),
    ("DonCaTaiTu_Act", "Performance", "Đờn ca tài tử (trình diễn)", "activity"),
    ("TauCa", "VehicleVessel", "Tàu cá", "object"),
    ("DanNhacNguAm", "MusicalInstrument", "Dàn nhạc Ngũ âm", "object"),
    ("DanKim", "MusicalInstrument", "Đàn kìm", "object"),
    ("DanTranh", "MusicalInstrument", "Đàn tranh", "object"),
    ("SongLan", "MusicalInstrument", "Song lan", "object"),
    ("GuitarPhimLom", "MusicalInstrument", "Guitar phím lõm", "object"),
    ("ChuaKhmer", "PracticeVenue", "Chùa Khmer / sân chùa", "venue"),
    ("TrongGiaDinh", "PracticeVenue", "Trong gia đình", "venue"),
    ("MieuNeakTa", "PracticeVenue", "Miếu Néak Tà (phum sóc)", "venue"),
    ("NguDan", "RoleType", "Ngư dân", "role"),
]
USES = [("DienTauNguAm", "DanNhacNguAm"), ("DonCaTaiTu_Act", "DanKim"), ("DonCaTaiTu_Act", "DanTranh"),
        ("DonCaTaiTu_Act", "SongLan"), ("DonCaTaiTu_Act", "GuitarPhimLom")]
# (ex-iri, class, nhãn)
CONCEPTS = [
    ("ThanNamHai", "MythicalBeing", "Thần Nam Hải (Cá Ông)"),
    ("ThanhHoang", "MythicalBeing", "Thành hoàng"),
    ("BaChuaXu", "MythicalBeing", "Bà Chúa Xứ"),
    ("NguyenTrungTruc", "HistoricalFigure", "Nguyễn Trung Trực"),
    ("PhatGiaoNamTong", "BeliefSystem", "Phật giáo Nam tông"),
    ("TinNguongThoThanhHoang", "BeliefSystem", "Tín ngưỡng thờ Thành hoàng"),
    ("VaiChan", "ArtisticElement", "Vai chằn (Dù Kê)"),
    ("BaiBanTo20", "ArtisticElement", "20 bài bản tổ (Đờn ca tài tử)"),
    ("NguoiKinh", "CommunityGroup", "Người Kinh"),
    ("NguoiCham", "CommunityGroup", "Người Chăm"),
    ("NguoiHoa", "CommunityGroup", "Người Hoa"),
    ("NguoiNamBo", "CommunityGroup", "Người Nam Bộ"),
]

# --------------------------------------------------------------------------
# 20 di sản. existing=True: individual đã tạo trong gen_ich_owl.build_abox (chỉ bổ sung).
# rules: (suffix, calendar, (ms, ds), (me, de), strength, tolDays, tolMonths, monthName, comment)
#        (ms, ds) = (None, d) cho rule khmer_lunar chưa chốt số tháng.
# --------------------------------------------------------------------------
U, V, P = "SocialPracticesRitualsFestive", "LeHoiTruyenThong", "PerformingArts"
H = {
    1: dict(key="ChoNoiCaiRang", existing=True, cls="PracticeHeritage", reg="listed"),
    2: dict(key="KyYenDinhBinhThuy", cls="EventHeritage", label="Lễ hội Kỳ Yên đình Bình Thủy", unesco=U, vn=V,
            loc="DinhBinhThuy", figures=["ThanhHoang"], beliefs=["TinNguongThoThanhHoang"], reg="listed",
            alt=dict(noacc="Le hoi Ky Yen dinh Binh Thuy"),
            rules=[("ThuongDien", "vn_lunar", (4, 12), (4, 15), "soft", 1, 0, None,
                    "Thượng điền; dsvh ghi 12–15/4 âm, báo ghi 12–14/4 âm; 2025 bắt đầu 11/4 âm."),
                   ("HaDien", "vn_lunar", (12, 14), (12, 15), "soft", 1, 0, None, "Hạ điền 14(–15)/12 âm.")]),
    3: dict(key="OocOmBocSocTrang", existing=True, cls="EventHeritage", reg="listed",
            rules=[("Khmer", "khmer_lunar", (None, 15), (None, 15), "hard", 0, 0, "Kadeuk",
                    "Ngày 15 tháng Kadeuk lịch Khmer (CSV). Số thứ tự tháng Khmer chưa chốt nên chỉ ghi monthName."),
                   ("VnApprox", "vn_lunar", (10, 14), (10, 15), "approx", 2, 1, None,
                    "Quy đổi xấp xỉ sang âm Việt (rằm tháng 10); năm 2025 lệch 1 tháng (đua 4–5/11/2025 = 15–16/9 âm Việt).")]),
    4: dict(key="OkOmBokTraVinh", cls="EventHeritage", label="Lễ hội Ok Om Bok Trà Vinh", unesco=U, vn=V,
            loc="AoBaOm", acts=["LeCungTrang", "DuaGheNgo"], cues=["SongLongBinh"], bearers=["DongBaoKhmer"], reg="listed",
            alt=dict(noacc="Ok Om Bok Tra Vinh", khmer="Ok Om Bok", local="Lễ cúng trăng"),
            rules=[("Khmer", "khmer_lunar", (None, 14), (None, 15), "hard", 0, 0, "Ka-đâk", "14–15 tháng Ka-đâk lịch Khmer (CSV)."),
                   ("VnApprox", "vn_lunar", (10, 13), (10, 16), "approx", 5, 1, None,
                    "≈ 13–16/10 âm Việt; tuần lễ VH–DL rộng hơn cửa sổ; 2014 và 2025 lệch 1 tháng (CSV notes).")]),
    5: dict(key="HoiDuaBoBayNui", cls="EventHeritage", label="Hội đua bò Bảy Núi", unesco=U, vn=V,
            loc="SanDuaBoTaPa", acts=["DuaBo"], bearers=["DongBaoKhmer"], assoc="SeneDolta", reg="listed",
            alt=dict(noacc="Hoi dua bo Bay Nui"),
            rules=[("VnApprox", "vn_lunar", (8, 29), (9, 1), "approx", 3, 1, None,
                    "Tổ chức nhân dịp Sene Dolta, không trùng đúng ngày; cửa sổ mượn của Sene Dolta, nới ±3 ngày ±1 tháng (CSV: 30/8, 27/8, 29/7 âm).")]),
    6: dict(key="NghinhOngTranDe", cls="EventHeritage", label="Lễ hội Nghinh Ông Trần Đề", unesco=U, vn=V,
            loc="LangOngNamHaiTranDe", acts=["LeNghinhThanNamHai"], cues=["TauCa"], roles=["NguDan"], figures=["ThanNamHai"], reg="listed",
            alt=dict(noacc="Le hoi Nghinh Ong Tran De", listing="Lễ hội Nghinh Ông"),
            rules=[("Main", "vn_lunar", (3, 21), (3, 23), "soft", 1, 0, None, "21–23/3 âm (dsvh: bắt đầu 21/3 âm).")]),
    7: dict(key="NghinhOngSongDoc", cls="EventHeritage", label="Lễ hội Nghinh Ông Sông Đốc", unesco=U, vn=V,
            loc="LangOngSongDoc", acts=["LeNghinhThanNamHai"], roles=["NguDan"], figures=["ThanNamHai"], reg="listed",
            alt=dict(noacc="Le hoi Nghinh Ong Song Doc"),
            rules=[("Main", "vn_lunar", (2, 14), (2, 16), "soft", 3, 0, None, "14–16/2 âm; 2025 chuỗi hoạt động 12–18/2 âm.")]),
    8: dict(key="ViaBaChuaXuNuiSam", cls="EventHeritage", label="Lễ hội Vía Bà Chúa Xứ núi Sam", unesco=U, vn=V,
            loc="MieuBaChuaXuNuiSam", acts=["RuocTuongBa"], figures=["BaChuaXu"],
            bearers=["NguoiKinh", "DongBaoKhmer", "NguoiCham", "NguoiHoa"], reg="listed", unesco_listing="2024-12-04",
            alt=dict(noacc="Le hoi Via Ba Chua Xu nui Sam", listing="Lễ hội Miếu Bà Chúa Xứ núi Sam"),
            rules=[("Main", "vn_lunar", (4, 22), (4, 27), "soft", 8, 0, None, "22–27/4 âm; 2025 cả đợt 14–27/4 âm.")]),
    9: dict(key="LeHoiDinhNguyenTrungTruc", cls="EventHeritage", label="Lễ hội đình thần Nguyễn Trung Trực", unesco=U, vn=V,
            loc="DinhThanNguyenTrungTruc", figures=["NguyenTrungTruc"], reg="listed",
            alt=dict(noacc="Le hoi dinh than Nguyen Trung Truc"),
            rules=[("Main", "vn_lunar", (8, 26), (8, 28), "soft", 1, 0, None, "26–28/8 âm (giỗ Cụ Nguyễn).")]),
    10: dict(key="ViaBaThuyLong", cls="EventHeritage", label="Lễ hội Vía Bà Thủy Long", unesco=U, vn=V,
             loc="Place_CaMauOldArea", reg="unverified", alt=dict(noacc="Le hoi Via Ba Thuy Long"),
             rules=[("Main", "vn_lunar", (2, 15), (2, 17), "soft", 0, 0, None, "15–17/2 âm theo Prompt 1: [chưa verify].")]),
    11: dict(key="CungBienMyLong", cls="EventHeritage", label="Lễ hội cúng biển Mỹ Long", unesco=U, vn=V,
             loc="MieuBaChuaXuMyLong", acts=["LeNghinhThanNamHai", "LeTeThanNong", "TongTau"], reg="listed",
             alt=dict(noacc="Le hoi cung bien My Long"),
             rules=[("Main", "vn_lunar", (5, 10), (5, 12), "soft", 0, 0, None, "10–12/5 âm; tống tàu 12/5.")]),
    12: dict(key="CholChnamThmay", existing=True, cls="EventHeritage", loc="Place_DBSCL",
             bearers=["DongBaoKhmer"], beliefs=["PhatGiaoNamTong"], cues=["ChuaKhmer", "TrongGiaDinh"], reg="not_listed",
             rules=[("Main", "solar", (4, 13), (4, 16), "soft", 1, 0, None,
                     "Giữa tháng 4 dương lịch, 3 ngày (theo lịch Khmer thiên văn); 2023–2025: 13–16/4.")]),
    13: dict(key="SeneDolta", existing=True, cls="EventHeritage", loc="Place_DBSCL", unesco=U,
             bearers=["DongBaoKhmer"], beliefs=["PhatGiaoNamTong"], cues=["ChuaKhmer", "TrongGiaDinh"], reg="not_listed",
             rules=[("Khmer", "khmer_lunar", (None, None), (None, None), "hard", 0, 0, None,
                     "3 ngày chính theo lịch Khmer; tên/số tháng Khmer: [chưa verify]."),
                    ("VnApprox", "vn_lunar", (8, 29), (9, 1), "approx", 1, 1, None,
                     "Việt hóa 29/8–1/9 âm (vắt tháng); đúng 2023, 2024; 2025 lệch 1 tháng (30/7–2/8 âm).")]),
    14: dict(key="DuKe", cls="PracticeHeritage", label="Nghệ thuật sân khấu Dù Kê", unesco=P, vn="NgheThuatTrinhDienDanGian",
             loc="Place_SocTrangArea", realized_by="HatDuKe", artistic=["VaiChan"], bearers=["DongBaoKhmer"], reg="listed",
             alt=dict(noacc="Nghe thuat san khau Du Ke")),
    15: dict(key="RoBamSocTrang", cls="PracticeHeritage", label="Nghệ thuật Rô-băm (Sóc Trăng)", unesco=P, vn="NgheThuatTrinhDienDanGian",
             loc="Place_SocTrangArea", realized_by="MuaRoBam", bearers=["DongBaoKhmer"], reg="listed",
             alt=dict(noacc="Nghe thuat Ro bam", khmer="Robam")),
    16: dict(key="MuaRomVong_Heritage", existing=True, cls="PracticeHeritage", vn="NgheThuatTrinhDienDanGian",
             loc="Place_SocTrangArea", bearers=["DongBaoKhmer"], reg="listed"),
    17: dict(key="NhacNguAmSocTrang", cls="PracticeHeritage", label="Nhạc ngũ âm Khmer (Sóc Trăng)", unesco=P, vn="NgheThuatTrinhDienDanGian",
             loc="Place_SocTrangArea", realized_by="DienTauNguAm", cues=["DanNhacNguAm", "ChuaKhmer"], bearers=["DongBaoKhmer"],
             reg="unverified", alt=dict(noacc="Nhac ngu am Khmer", khmer="Pinn Peat")),
    18: dict(key="DonCaTaiTu", cls="PracticeHeritage", label="Đờn ca tài tử Nam Bộ", unesco=P, vn="NgheThuatTrinhDienDanGian",
             loc="Place_NamBo", realized_by="DonCaTaiTu_Act", cues=["DanKim", "DanTranh", "SongLan", "GuitarPhimLom"],
             artistic=["BaiBanTo20"], bearers=["NguoiNamBo"], reg="listed", unesco_listing="2013-12-05",
             alt=dict(noacc="Don ca tai tu Nam Bo")),
    19: dict(key="ChroiRumChek", cls="EventHeritage", label="Lễ hội Chrôi Rum Chếk (Phước Biển)", unesco=U, vn=V,
             loc="TrungTamChroiRumChek", bearers=["DongBaoKhmer"], reg="listed",
             alt=dict(noacc="Le hoi Chroi Rum Chek", local="Lễ hội Phước Biển"),
             rules=[("Main", "vn_lunar", (2, 13), (2, 15), "soft", 1, 0, None, "13–15/2 âm (nguồn trước: 14–15/2 âm).")]),
    20: dict(key="DomLongNeakTa", cls="EventHeritage", label="Lễ hội Đom Lơng Néak Tà", unesco=U,
             loc="Place_TraVinhArea", cues=["MieuNeakTa"], bearers=["DongBaoKhmer"], reg="unverified",
             alt=dict(noacc="Le hoi Dom Long Neak Ta"),
             rules=[("Main", "vn_lunar", (3, 1), (5, 30), "soft", 0, 0, None,
                     "Mỗi phum sóc chọn ngày riêng trong tháng 3–5 âm; không có ngày chung → B4 chỉ dùng như cue yếu.")]),
}
VNCAT_LABEL = {"LeHoiTruyenThong": "Lễ hội truyền thống", "TapQuanXaHoiVaTinNguong": "Tập quán xã hội và tín ngưỡng",
               "NgheThuatTrinhDienDanGian": "Nghệ thuật trình diễn dân gian"}

# Occurrence (id, năm) -> (start, end | None, (lms, lds, lme, lde) | None, venue, ghi chú suy diễn)
OCC = {
    (2, 2023): ("2023-05-30", "2023-06-02", (4, 12, 4, 15), "DinhBinhThuy", None),
    (2, 2024): ("2024-05-19", "2024-05-21", (4, 12, 4, 14), "DinhBinhThuy", None),
    (2, 2025): ("2025-05-08", "2025-05-12", (4, 11, 4, 15), "DinhBinhThuy", None),
    (3, 2023): ("2023-11-25", "2023-11-27", (10, 13, 10, 15), "SongMaspero_CauQuay_CauCao",
                "Ngày âm của 25/11 suy từ mốc 26/11 = 14/10 âm trong CSV."),
    (3, 2024): ("2024-11-14", "2024-11-15", (10, 14, 10, 15), "SongMaspero_CauQuay_CauCao", None),
    (3, 2025): ("2025-11-03", "2025-11-05", (9, 14, 9, 16), "SongMaspero_CauQuay_CauCao",
                "Ngày âm của 3/11 suy từ mốc 4/11 = 15/9 âm trong CSV. Cúng trăng tại chùa Khleang."),
    (4, 2024): ("2024-11-09", "2024-11-15", (10, 9, 10, 15), "AoBaOm",
                "Ngày âm suy từ 14/11/2024 = 14/10 âm (CSV dòng #3 cùng năm)."),
    (4, 2025): ("2025-10-30", "2025-11-05", (9, 10, 9, 16), "AoBaOm", "Ngày âm của 30/10 suy từ mốc 5/11 = 16/9 âm."),
    (5, 2023): ("2023-10-14", "2023-10-14", (8, 30, 8, 30), "SanDuaBoTaPa", None),
    (5, 2024): ("2024-09-29", "2024-09-29", (8, 27, 8, 27), "SanDuaBoVinhTrung", None),
    (5, 2025): ("2025-09-20", "2025-09-20", (7, 29, 7, 29), "SanDuaBoTaPa", None),
    (7, 2025): ("2025-03-11", "2025-03-17", (2, 12, 2, 18), "LangOngSongDoc", None),
    (8, 2025): ("2025-05-11", "2025-05-24", (4, 14, 4, 27), "MieuBaChuaXuNuiSam", None),
    (9, 2023): ("2023-10-10", None, (8, 26, None, None), "DinhThanNguyenTrungTruc",
                "Chỉ có ngày khai mạc; ngày kết thúc chưa có nguồn nên không ghi endDate."),
    (12, 2023): ("2023-04-14", "2023-04-16", None, "Place_DBSCL", "Rơi vào tháng 2 nhuận âm Việt nên không ghi ngày âm."),
    (12, 2024): ("2024-04-13", "2024-04-16", (3, 5, 3, 8), "Place_DBSCL", None),
    (12, 2025): ("2025-04-14", "2025-04-16", (3, 17, 3, 19), "Place_DBSCL", None),
    (13, 2023): ("2023-10-13", "2023-10-15", (8, 29, 9, 1), "Place_DBSCL", None),
    (13, 2024): ("2024-10-01", "2024-10-03", (8, 29, 9, 1), "Place_DBSCL", None),
    (13, 2025): ("2025-09-21", "2025-09-23", (7, 30, 8, 2), "Place_DBSCL", None),
    (19, 2025): ("2025-03-12", "2025-03-14", (2, 13, 2, 15), "TrungTamChroiRumChek", None),
}
SKIP_OCC = {1: "Ngày hội Du lịch là sự kiện du lịch gắn di sản, không phải occurrence (CSV notes); PracticeHeritage không có Occurrence."}

PAIRS = [
    ("Pair_C1", "OocOmBocSocTrang", "OkOmBokTraVinh", ["place"],
     "Cùng lễ cúng trăng và đua ghe Ngo của người Khmer; phân biệt bằng địa điểm (sông Maspéro/Sóc Trăng vs Ao Bà Om, sông Long Bình/Trà Vinh)."),
    ("Pair_C2", "NghinhOngTranDe", "NghinhOngSongDoc", ["place", "temporal"],
     "Cùng tên 'Nghinh Ông' (dsvh có ≥3 mục trùng tên); phân biệt bằng địa điểm và cửa sổ âm lịch 21–23/3 vs 14–16/2."),
    ("Pair_C3", "NghinhOngSongDoc", "ChroiRumChek", ["place", "cue"],
     "Cửa sổ âm lịch chồng lấn (14–16/2 vs 13–15/2), cùng lễ hội vùng biển; phân biệt bằng địa điểm và cue Khmer."),
    ("Pair_C4", "HoiDuaBoBayNui", "SeneDolta", ["cue"],
     "Diễn ra cùng dịp; ảnh có bò đua/sân đua → Hội đua bò, cảnh chùa/cúng ông bà → Sene Dolta."),
]


# --------------------------------------------------------------------------
def _clean(s):
    return (s or "").strip()


def _unver(*vals):
    return any("[chưa verify]" in _clean(v) or "chưa đối chiếu" in _clean(v) or "nguồn thứ cấp" in _clean(v)
               or "Prompt 1" in _clean(v) for v in vals)


def _dt(d):
    return Literal(d + "T00:00:00", datatype=XSD.dateTime)


def build(g, ind, add, kind, alt, csv_dir):
    global ICH, EX
    import gen_ich_owl as gen
    ICH, EX = gen.ICH, gen.EX
    csv_dir = Path(csv_dir)
    rows = {int(r["id"]): r for r in csv.DictReader(open(csv_dir / "20_di_san_verify.csv", encoding="utf-8-sig"))}
    occ_rows = {(int(r["heritage_id"]), int(r["year"])): r
                for r in csv.DictReader(open(csv_dir / "20_di_san_occurrence_2023_2025.csv", encoding="utf-8-sig"))}
    assert set(rows) == set(H), "CSV và bảng curated phải cùng 20 id"
    lit = lambda v, lang="vi": Literal(v, lang=lang)

    # ---- không gian / hành chính ----
    for key, (cls, label, within) in PLACES.items():
        node = EX[key]
        if cls:
            ind(node, ICH[cls], label)
        if within:
            add(node, ICH.locatedWithin, EX[within])
    for key, (label, covers, era, succ) in ADMINS.items():
        node = EX[key]
        if label:
            ind(node, ICH.AdminUnit, label, comment=NQ202_NOTE)
            g.add((node, ICH.adminLevel, Literal("province")))
            g.add((node, ICH.validTo if era == "pre" else ICH.validFrom,
                   _dt("2025-06-11" if era == "pre" else "2025-06-12")))
            add(node, ICH.coversPlace, EX[covers])
        if succ:
            add(node, ICH.succeededBy, EX[succ])

    # ---- từ vựng ----
    for iri, cls, label, ck in VOCAB:
        ind(ICH[iri], ICH[cls], label, comment="Theo Khung thực thể / cột notes-venue của CSV; chưa đối chiếu hồ sơ gốc.")
        if ck:
            kind(ICH[iri], ck)
    for a, o in USES:
        add(ICH[a], ICH.usedObjectOfType, ICH[o])
    for iri, cls, label in CONCEPTS:
        ind(EX[iri], ICH[cls], label)
    ind(ICH.NgheThuatTrinhDienDanGian, ICH.VnCategory, "Nghệ thuật trình diễn dân gian")

    # ---- di sản ----
    labels = {hid: (H[hid].get("label") or str(g.value(EX[H[hid]["key"]], RDFS.label))) for hid in H}
    for hid in sorted(H):
        h, r = H[hid], rows[hid]
        node = EX[h["key"]]
        status = "verified" if r["verify_level"].startswith("Cao") and not _unver(r["qd_number"], r["qd_date"]) else "unverified"
        if not h.get("existing"):
            ind(node, ICH[h["cls"]], h["label"], status=status)
        g.add((node, ICH.datasetId, Literal(hid)))
        g.add((node, ICH.registryStatus, Literal(h["reg"])))
        if h.get("alt"):
            alt(node, **h["alt"])
        if not h.get("existing") and h["reg"] != "not_listed":
            g.add((node, ICH.listingName, lit(_clean(r["registry_name"]).split(" (")[0])))
        for c, txt in [("Địa bàn gốc trong Danh mục", r["registry_location_original"]),
                       ("Địa bàn sau 2025 (CSV)", r["admin_after_2025"]), ("Quy tắc thời gian (CSV)", r["time_rule"]),
                       ("Ghi chú (CSV)", r["notes"]), ("Trạng thái khác (CSV)", r["other_status"]),
                       ("Mức verify (CSV)", r["verify_level"])]:
            if _clean(txt):
                g.add((node, RDFS.comment, lit(f"{c}: {_clean(txt)}")))
        for col in ("registry_name_source_url", "time_rule_source_url", "venue_source_url", "community_source_url"):
            for u in re.findall(r"https?://\S+", r.get(col, "")):
                g.add((node, ICH.source, Literal(u.rstrip(";,"), datatype=XSD.anyURI)))
        if h.get("unesco") and not h.get("existing"):
            add(node, ICH.unescoDomain, ICH[h["unesco"]])
        if h.get("unesco") and hid == 13:
            add(node, ICH.unescoDomain, ICH[h["unesco"]])
        if h.get("vn") and (not h.get("existing") or hid == 16):
            add(node, ICH.vnCategory, ICH[h["vn"]])
        if h.get("loc"):
            add(node, ICH.hasLocality, EX[h["loc"]])
        for a in h.get("acts", []):
            add(node, ICH.typicallyIncludes, ICH[a])
        for c in h.get("cues", []):
            cn = ICH[c] if (ICH[c], RDF.type, None) in g else EX[c]
            add(node, ICH.hasCue, cn)
            if cn == EX[c] and (cn, ICH.cueKind, None) not in g:
                kind(cn, "place")
        for ro in h.get("roles", []):
            add(node, ICH.involvesRole, ICH[ro])
        for f in h.get("figures", []):
            add(node, ICH.veneratesFigure, EX[f])
        for b in h.get("beliefs", []):
            add(node, ICH.hasBelief, EX[b])
        for b in h.get("bearers", []):
            add(node, ICH.bearerGroup, EX[b])
        for a in h.get("artistic", []):
            add(node, ICH.hasArtisticElement, EX[a])
        if h.get("realized_by"):
            add(ICH[h["realized_by"]], ICH.realizesPractice, node)
        if h.get("assoc"):
            add(node, ICH.associatedWithEvent, EX[h["assoc"]])

        # TemporalRule
        for suf, cal, (ms, ds), (me, de), strength, tol_d, tol_m, mname, note in h.get("rules", []):
            rn = EX[f"{h['key']}_Rule_{suf}"]
            rstatus = "unverified" if (strength == "approx" or _unver(r["time_rule"], note)) else status
            ind(rn, ICH.TemporalRule, f"Quy tắc thời gian – {labels[hid]} ({suf})", status=rstatus, comment=note)
            g.add((rn, ICH.calendarSystem, Literal(cal)))
            for p, v in [(ICH.monthStart, ms), (ICH.dayStart, ds), (ICH.monthEnd, me), (ICH.dayEnd, de)]:
                if v is not None:
                    g.add((rn, p, Literal(v)))
            g.add((rn, ICH.ruleStrength, Literal(strength)))
            g.add((rn, ICH.toleranceDays, Literal(tol_d, datatype=XSD.nonNegativeInteger)))
            g.add((rn, ICH.toleranceMonths, Literal(tol_m)))
            g.add((rn, ICH.recurrence, Literal("annual")))
            if mname:
                g.add((rn, ICH.monthName, Literal(mname)))
            add(node, ICH.hasTemporalRule, rn)

        # ListingEntry
        if h["reg"] != "not_listed":
            le = EX[f"Listing_{h['key']}_QG"]
            qd_unver = _unver(r["qd_number"], r["qd_date"]) or not re.match(r"^\d{4}-\d{2}-\d{2}$", _clean(r["qd_date"]))
            ind(le, ICH.ListingEntry, f"{labels[hid]} (Danh mục QG)", status="unverified" if qd_unver else "verified",
                comment=f"CSV: QĐ {_clean(r['qd_number'])}, ngày {_clean(r['qd_date'])}")
            g.add((le, ICH.listType, Literal("QG")))
            m = re.match(r"^(\d+/QĐ-BVHTTDL)", _clean(r["qd_number"]))
            if m:
                g.add((le, ICH.decisionNumber, Literal(m.group(1))))
            if re.match(r"^\d{4}-\d{2}-\d{2}", _clean(r["qd_date"])):
                g.add((le, ICH.decisionDate, _dt(_clean(r["qd_date"])[:10])))
            for u in re.findall(r"https?://\S+", r["qd_source_url"]) or [DSVH_LIST]:
                g.add((le, ICH.sourceURL, Literal(u.rstrip(";,"), datatype=XSD.anyURI)))
            add(node, ICH.hasListing, le)
        if h.get("unesco_listing"):
            lu = EX[f"Listing_{h['key']}_UNESCO"]
            ind(lu, ICH.ListingEntry, f"{labels[hid]} (UNESCO – Danh sách đại diện)",
                comment=f"CSV other_status: {_clean(r['other_status'])}")
            g.add((lu, ICH.listType, Literal("UNESCO")))
            g.add((lu, ICH.decisionDate, _dt(h["unesco_listing"])))
            for u in re.findall(r"https?://\S+", r["other_status"] + " " + r["notes"]):
                if not any(k in u for k in ("bvhttdl", "vietnamplus", "unesco")):
                    continue
                g.add((lu, ICH.sourceURL, Literal(u.rstrip(";,"), datatype=XSD.anyURI)))
            add(node, ICH.hasListing, lu)

    # ---- Occurrence ----
    for (hid, year), row in sorted(occ_rows.items()):
        if hid in SKIP_OCC:
            g.add((EX[H[hid]["key"]], RDFS.comment, lit(f"Mốc {year} trong CSV occurrence bị bỏ qua: {SKIP_OCC[hid]}")))
            continue
        start, end, lunar, venue, derived = OCC[(hid, year)]
        on = EX[f"{H[hid]['key']}_{year}"]
        ind(on, ICH.Occurrence, f"{labels[hid]} {year}", status="unverified",
            source=_clean(row["source_url"]), comment="CSV: " + _clean(row["actual_dates_and_lunar_equivalent"]))
        if derived:
            g.add((on, RDFS.comment, lit("Suy diễn: " + derived)))
        add(on, ICH.occurrenceOf, EX[H[hid]["key"]])
        g.add((on, ICH.startDate, _dt(start)))
        if end:
            g.add((on, ICH.endDate, _dt(end)))
        if lunar:
            for p, v in zip([ICH.lunarStartMonth, ICH.lunarStartDay, ICH.lunarEndMonth, ICH.lunarEndDay], lunar):
                if v is not None:
                    g.add((on, p, Literal(v)))
        add(on, ICH.tookPlaceAt, EX[venue])
        if (hid, year) == (3, 2025):
            add(on, ICH.tookPlaceAt, EX.ChuaKhleang)
    missing = set(OCC) - set(occ_rows)
    assert not missing, f"OCC curated có dòng không có trong CSV: {missing}"

    # ---- cặp dễ nhầm ----
    for pid, a, b, kinds, note in PAIRS:
        p = ind(EX[pid], ICH.ConfusablePair, f"Cặp dễ nhầm: {labels[_id(a)]} / {labels[_id(b)]}")
        add(p, ICH.hasMember, EX[a], EX[b])
        add(EX[a], ICH.confusableWith, EX[b])
        for k in kinds:
            g.add((p, ICH.discriminatorKind, Literal(k)))
        g.add((p, ICH.discriminatorNote, lit(note)))
    # đặt nhãn cho các nút đã có trong gen_ich_owl nhưng thiếu nhãn
    for pid in ("Pair_A1", "Pair_B1", "Pair_B2", "Pair_B3", "Part_001"):
        if (EX[pid], RDFS.label, None) not in g:
            g.add((EX[pid], RDFS.label, lit(pid.replace("_", " "))))


def _id(key):
    return next(i for i, h in H.items() if h["key"] == key)
