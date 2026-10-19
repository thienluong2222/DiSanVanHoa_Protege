#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_ich_owl.py  -  Sinh ich-tbox.ttl, ich-abox.ttl, ich-full.owl (rdflib). ABox nạp từ 2 CSV qua abox_registry.py.

Ontology di sản văn hóa phi vật thể (ICH) phục vụ nhận diện ảnh/video.
- CIDOC CRM 7.1.3 chỉ align qua annotation `ich:crmMapping` (không import ECRM).
- Ghi [chưa verify] khi không có nguồn; không suy đoán.

Chạy:  python3 gen_ich_owl.py [thư_mục_đầu_ra]
"""
import sys
from pathlib import Path
from rdflib import Graph, Namespace, URIRef, Literal, BNode, RDF, RDFS, OWL, XSD
from rdflib.collection import Collection

ICH = Namespace("https://w3id.org/ich-mekong/ontology#")
EX = Namespace("https://w3id.org/ich-mekong/data#")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
GEO = Namespace("http://www.opengis.net/ont/geosparql#")
TBOX_IRI = URIRef("https://w3id.org/ich-mekong/ontology")
ABOX_IRI = URIRef("https://w3id.org/ich-mekong/data")

CRM_BASE = "https://cidoc-crm.org/html/cidoc_crm_v7.1.3.html#"
PC14_URL = "http://www.cidoc-crm.org/cidoc-crm/PC14_carried_out_by"
# Scope note chưa đối chiếu (giữ nguyên danh sách từ Prompt 2)
UNVERIFIED_SCOPE = {"E22", "E24", "E29", "E32", "E33", "E39", "E99"}

# HermiT/Protégé không parse được literal geo:wktLiteral (ngoài OWL 2 datatype map) nên mặc định asWKT là xsd:string.
# Thêm cờ --wkt-typed để sinh bản dùng geo:wktLiteral đúng chuẩn GeoSPARQL (cho triple store; reasoner sẽ báo lỗi datatype).
WKT_TYPED = "--wkt-typed" in sys.argv

UNESCO_PDF = "https://ich.unesco.org/doc/src/01857-EN.pdf"
CSV_DIR = Path(__file__).resolve().parent   # chứa 20_di_san_verify.csv, 20_di_san_occurrence_2023_2025.csv
DSVH_LIST = "https://dsvh.gov.vn/danh-muc-di-san-van-hoa-phi-vat-the-quoc-gia-1789"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def crm(text, *ids):
    """Chuỗi crmMapping: mô tả + URL CIDOC CRM 7.1.3 (+ cờ chưa verify)."""
    s = text
    if ids:
        urls = [PC14_URL if i == "PC14" else CRM_BASE + i for i in ids]
        s += " | CIDOC CRM 7.1.3: " + " ; ".join(urls)
    unver = [i for i in ids if i in UNVERIFIED_SCOPE]
    if unver:
        s += " [chưa verify scope note: " + ", ".join(unver) + "]"
    return s


NONE = "custom - không có tương đương trong CIDOC CRM 7.1.3"


def lst(g, items):
    node = BNode()
    Collection(g, node, items)
    return node


def U(x):
    """Tên (str thuần) -> ICH URIRef; URIRef/BNode giữ nguyên (URIRef là con của str nên phải kiểm trước)."""
    if isinstance(x, (URIRef, BNode)):
        return x
    return ICH[x]


def union(g, *items):
    b = BNode()
    g.add((b, RDF.type, OWL.Class))
    g.add((b, OWL.unionOf, lst(g, [U(i) for i in items])))
    return b


def restr(g, prop, kind, n):
    """Cardinality (không qualified): kind in min|max|exact."""
    r = BNode()
    g.add((r, RDF.type, OWL.Restriction))
    g.add((r, OWL.onProperty, U(prop)))
    pred = {"min": OWL.minCardinality, "max": OWL.maxCardinality, "exact": OWL.cardinality}[kind]
    g.add((r, pred, Literal(n, datatype=XSD.nonNegativeInteger)))
    return r


def data_enum(g, values):
    dt = BNode()
    g.add((dt, RDF.type, RDFS.Datatype))
    g.add((dt, OWL.oneOf, lst(g, [Literal(v) for v in values])))
    return dt


def int_range(g, lo, hi):
    dt = BNode()
    g.add((dt, RDF.type, RDFS.Datatype))
    g.add((dt, OWL.onDatatype, XSD.integer))
    r1, r2 = BNode(), BNode()
    g.add((r1, XSD.minInclusive, Literal(lo)))
    g.add((r2, XSD.maxInclusive, Literal(hi)))
    g.add((dt, OWL.withRestrictions, lst(g, [r1, r2])))
    return dt


def pos_decimal(g):
    dt = BNode()
    g.add((dt, RDF.type, RDFS.Datatype))
    g.add((dt, OWL.onDatatype, XSD.decimal))
    r1 = BNode()
    g.add((r1, XSD.minExclusive, Literal("0", datatype=XSD.decimal)))
    g.add((dt, OWL.withRestrictions, lst(g, [r1])))
    return dt


def all_disjoint(g, classes):
    b = BNode()
    g.add((b, RDF.type, OWL.AllDisjointClasses))
    g.add((b, OWL.members, lst(g, [U(c) for c in classes])))


def pair_disjoint(g, a, b):
    g.add((U(a), OWL.disjointWith, U(b)))


def annotate(g, node, vi_label, en_label, vi_comment, en_comment):
    g.add((node, RDFS.label, Literal(vi_label, lang="vi")))
    g.add((node, RDFS.label, Literal(en_label, lang="en")))
    g.add((node, RDFS.comment, Literal(vi_comment, lang="vi")))
    g.add((node, RDFS.comment, Literal(en_comment, lang="en")))


# --------------------------------------------------------------------------
# TBox
# --------------------------------------------------------------------------
# (name, parent, nerLabel(s), crmMapping, vi_label, en_label, vi_comment, en_comment, optional)
CLASSES = [
    ("CueBearer", None, None, NONE, "Nút mang cue", "Cue bearer",
     "Nút có thể mang cue nhận diện: di sản thật (HeritageElement) hoặc nút gây nhầm (LookalikeElement); để idf đếm được cả hai.",
     "A node that may carry recognition cues: a real heritage element or a lookalike; lets idf count both.", False),
    ("HeritageElement", "CueBearer", ["CULTURAL_HERITAGE"], crm("E55 ⊂ E28", "E55", "E28"),
     "Di sản", "Heritage element",
     "Đơn vị di sản phi vật thể ở mức loại hình; chỉ nhánh này được trả làm đáp án.",
     "A named heritage element at type level; only this branch may be returned as an answer.", False),
    ("EventHeritage", "HeritageElement", ["CULTURAL_EVENT"], crm("E55 (loại của E7)", "E55", "E7"),
     "Di sản sự kiện", "Event heritage",
     "Di sản định kỳ gắn cửa sổ thời gian, có TemporalRule.",
     "A recurring heritage tied to a calendar window.", False),
    ("PracticeHeritage", "HeritageElement", ["CULTURAL_FORM"], crm("E55", "E55"),
     "Di sản thực hành", "Practice heritage",
     "Di sản thực hành không có cửa sổ ngày.",
     "A heritage practice with no calendar window.", False),
    ("LookalikeElement", "CueBearer", None, NONE, "Nút gây nhầm", "Lookalike element",
     "Nút ngoài KG (vd chợ nổi khác) làm decoy để idf đúng và lập ConfusablePair; không bao giờ là đáp án.",
     "A node outside the KG (e.g. another floating market) used as a decoy for correct idf and ConfusablePair; never an answer.", False),
    ("HeritageDomain", None, ["CULTURAL_DOMAIN"], crm("E55", "E55"), "Lĩnh vực di sản", "Heritage domain",
     "Hệ phân loại lĩnh vực di sản.", "A vocabulary of heritage domains.", False),
    ("UnescoDomain", "HeritageDomain", ["CULTURAL_DOMAIN"], crm("E55", "E55"), "Lĩnh vực UNESCO", "UNESCO domain",
     "Năm lĩnh vực theo Công ước 2003.", "The five domains of the 2003 Convention.", False),
    ("VnCategory", "HeritageDomain", None, crm("E55", "E55"), "Loại hình theo pháp luật VN", "Vietnamese legal category",
     "Loại hình di sản theo pháp luật Việt Nam.", "Heritage categories under Vietnamese law.", False),
    ("Occurrence", None, None, crm("E7 + P4 → E52", "E7", "P4", "E52"), "Lần diễn ra", "Occurrence",
     "Một lần diễn ra cụ thể trong một năm.", "One yearly realisation.", False),
    ("TemporalRule", None, ["DATE_LUNAR", "DATE_SOLAR", "DURATION", "FREQUENCY"],
     "Không có tương đương (E52 không phù hợp)", "Quy tắc thời gian", "Temporal rule",
     "Quy tắc thời gian chuẩn của EventHeritage (khoảng ngày-tháng theo một hệ lịch).",
     "The canonical calendar rule of an EventHeritage (a day-month window in one calendar system).", False),
    ("TemporalCue", None, ["TIME_OF_DAY"], crm("E55", "E55"), "Cue thời gian", "Temporal cue",
     "Tín hiệu thời gian yếu (giờ trong ngày, mùa).", "A weak temporal cue (time of day, season).", False),
    ("Place", None, ["LOCATION"], crm("E53", "E53"), "Địa điểm", "Place",
     "Tham chiếu không gian ổn định.", "A stable spatial referent.", False),
    ("CulturalSpace", "Place", ["CULTURAL_SPACE"], crm("E22/E24 + P156", "E22", "E24", "P156"),
     "Không gian văn hóa", "Cultural space",
     "Công trình hay không gian cố định gắn thực hành văn hóa.", "A fixed structure or space tied to a cultural practice.", False),
    ("NaturalFeature", "Place", ["NATURAL_FEATURE"], crm("E26 + P156", "E26", "P156"),
     "Đối tượng tự nhiên", "Natural feature",
     "Đối tượng tự nhiên có tên (sông, rạch).", "A named natural feature (river, canal).", False),
    ("AdminUnit", None, ["GEOPOLITICAL_ENTITY"], crm("E4 + P7", "E4", "P7"), "Đơn vị hành chính", "Administrative unit",
     "Đơn vị hành chính có tên và hiệu lực; tách khỏi Place ổn định, nối qua coversPlace.",
     "An administrative unit with a name and validity period; separate from the stable Place, linked via coversPlace.", False),
    ("CulturalFigure", None, ["CULTURAL_FIGURE"], "trừu tượng (abstract), không ánh xạ trực tiếp",
     "Nhân vật văn hóa", "Cultural figure",
     "Chủ thể tinh thần được tưởng niệm hoặc quy chiếu niềm tin.", "A commemorated spiritual subject.", False),
    ("MythicalBeing", "CulturalFigure", ["MYTHICAL_BEING"], crm("E28", "E28"), "Thần linh / nhân vật thần thoại", "Mythical being",
     "Thần linh, nhân vật thần thoại.", "A deity or mythical character.", False),
    ("HistoricalFigure", "CulturalFigure", ["HISTORICAL_FIGURE"], crm("E21", "E21"), "Nhân vật lịch sử", "Historical figure",
     "Nhân vật được coi là có thật.", "A person documented as historical.", False),
    ("Agent", None, ["AGENT"], crm("E39", "E39"), "Tác nhân", "Agent",
     "Chủ thể hành động có chủ đích.", "An intentional actor.", False),
    ("Person", "Agent", ["PERSON"], crm("E21", "E21"), "Cá nhân", "Person",
     "Cá nhân cụ thể có tên (vai trò xã hội nằm ở Participation, không phải subclass).", "A named individual (social roles live in Participation, not subclasses).", False),
    ("Group", "Agent", ["GROUP"], crm("E74", "E74"), "Nhóm", "Group",
     "Tập hợp người, không nhất thiết có tư cách pháp lý.", "A collection of people, not necessarily a legal body.", False),
    ("CommunityGroup", "Group", ["COMMUNITY_GROUP"], crm("E74 + P2", "E74", "P2"), "Nhóm cộng đồng", "Community group",
     "Cộng đồng xã hội nắm giữ di sản.", "A bearer community.", False),
    ("Organization", "Group", ["ORGANIZATION"], crm("E74 + P2", "E74", "P2"), "Tổ chức", "Organization",
     "Tổ chức có tư cách hành chính/pháp lý.", "A legal organisation.", False),
    ("PerformingTroupe", "Organization", ["PERFORMING_TROUPE"], crm("E74 + P2", "E74", "P2"), "Đoàn nghệ thuật", "Performing troupe",
     "Đoàn nghệ thuật.", "A performing troupe.", False),
    ("Organizer", "Organization", ["ORGANIZER"], crm("E74 + P2; P14", "E74", "P2", "P14"), "Đơn vị tổ chức", "Organizer",
     "Đơn vị tổ chức lễ hội/sự kiện.", "A body organising an event.", False),
    ("RoleType", None, ["PRACTITIONER"], crm("E55 (range P14.1)", "E55", "P14"), "Vai trò", "Role type",
     "Vai trò xã hội của người thực hành (ngư dân, thương hồ, con dầm...).", "A practitioner's social role.", False),
    ("Participation", None, None, crm("PC14 = P14 + P14.1", "PC14", "P14"), "Sự tham gia", "Participation",
     "(Optional) Sự tham gia của một agent với một vai trò trong một activity.", "(Optional) An agent's role in an activity.", True),
    ("ActivityType", None, ["CULTURAL_ACTIVITY"], crm("E55 (loại của E7)", "E55", "E7"), "Loại hoạt động văn hóa", "Activity type",
     "Loại hoạt động văn hóa ở mức type (Lễ cúng trăng, đua ghe Ngo...).", "A type of cultural activity at type level.", False),
    ("Ritual", "ActivityType", ["RITUAL"], crm("E55", "E55"), "Nghi lễ", "Ritual",
     "Loại nghi lễ có trình tự và ý nghĩa tín ngưỡng.", "A type of ceremonial procedure.", False),
    ("Performance", "ActivityType", ["PERFORMANCE"], crm("E55", "E55"), "Trình diễn", "Performance",
     "Loại hoạt động trình diễn nghệ thuật.", "A type of artistic performance.", False),
    ("SocialPractice", "ActivityType", ["SOCIAL_PRACTICE"], crm("E55", "E55"), "Tập quán xã hội", "Social practice",
     "Loại tập quán xã hội, gồm trò chơi và cuộc thi.", "A type of social custom, including games and contests.", False),
    ("CulturalActivity", None, None, crm("E7; phân loại qua P2 → ActivityType", "E7", "P2"), "Hoạt động văn hóa (instance)", "Cultural activity (instance)",
     "(Optional) Hành động cụ thể diễn ra trong một Occurrence.", "(Optional) A concrete action within an occurrence.", True),
    ("PracticeVenue", None, ["PRACTICE_VENUE"], crm("E55", "E55"), "Không gian thực hành", "Practice venue",
     "Loại bối cảnh thực hành (trên ghe, sân chùa, mặt sông đông ghe).", "A type of practice setting.", False),
    ("CulturalArtifact", None, ["CULTURAL_ARTIFACT"], crm("E55 + P125", "E55", "P125"), "Vật phẩm văn hóa", "Cultural artifact",
     "Loại vật phẩm gắn với thực hành.", "A type of object tied to a practice.", False),
    ("Offering", "CulturalArtifact", ["OFFERING"], crm("E55 + P125", "E55", "P125"), "Lễ vật", "Offering",
     "Lễ vật.", "An offering.", False),
    ("MusicalInstrument", "CulturalArtifact", ["MUSICAL_INSTRUMENT"], crm("E55 + P125", "E55", "P125"), "Nhạc cụ", "Musical instrument",
     "Nhạc cụ.", "A musical instrument.", False),
    ("VehicleVessel", "CulturalArtifact", ["VEHICLE_VESSEL"], crm("E55 + P125", "E55", "P125"), "Phương tiện (ghe thuyền)", "Vehicle / vessel",
     "Phương tiện di chuyển, chủ yếu ghe thuyền.", "A means of transport, mainly boats.", False),
    ("ToolEquipment", "CulturalArtifact", ["TOOL_EQUIPMENT"], crm("E55 + P125", "E55", "P125"), "Công cụ / dụng cụ", "Tool / equipment",
     "Công cụ, dụng cụ.", "A tool or piece of equipment.", False),
    ("Costume", "CulturalArtifact", ["COSTUME"], crm("E55 + P125", "E55", "P125"), "Trang phục", "Costume",
     "Y phục truyền thống.", "Traditional dress.", False),
    ("CulturalConcept", None, ["CULTURAL_CONCEPT"], "trừu tượng (abstract), không ánh xạ trực tiếp",
     "Khái niệm văn hóa", "Cultural concept",
     "Khái niệm trừu tượng gắn với di sản.", "An abstract heritage concept.", False),
    ("Significance", "CulturalConcept", ["SIGNIFICANCE"], crm("E55", "E55"), "Ý nghĩa", "Significance",
     "Ý nghĩa biểu tượng.", "Symbolic meaning.", False),
    ("Purpose", "CulturalConcept", ["PURPOSE"], crm("E55 (range P21)", "E55", "P21"), "Mục đích", "Purpose",
     "Mục đích của hành vi.", "Purpose of an act.", False),
    ("OriginStory", "CulturalConcept", ["ORIGIN_STORY"], crm("E73 + P129⁻", "E73", "P129"), "Sự tích", "Origin story",
     "Sự tích giải thích nguồn gốc.", "An origin narrative.", False),
    ("BeliefSystem", "CulturalConcept", ["BELIEF_SYSTEM"], crm("E55", "E55"), "Hệ thống tín ngưỡng", "Belief system",
     "Hệ thống tín ngưỡng hoặc tôn giáo.", "A belief system.", False),
    ("ArtisticElement", "CulturalConcept", ["ARTISTIC_ELEMENT"], crm("E55", "E55"), "Yếu tố nghệ thuật", "Artistic element",
     "Yếu tố nghệ thuật (bài bản, vai diễn).", "An artistic element (repertoire, role).", False),
    ("ConfusablePair", None, None, "Không có tương đương", "Cặp dễ nhầm", "Confusable pair",
     "Cặp dễ nhầm kèm discriminator (reify vì OWL không gắn thuộc tính lên property assertion).",
     "A confusable pair with discriminator (reified; OWL cannot annotate a property assertion).", False),
    ("ListingEntry", None, None, crm("E32", "E32"), "Mục Danh mục", "Listing entry",
     "Một mục trong Danh mục (quốc gia hoặc UNESCO) kèm số quyết định, ngày, nguồn.",
     "An entry in a national or UNESCO list with decision number, date and source.", False),
]

CUE_RANGE = ["ActivityType", "RoleType", "CulturalArtifact", "PracticeVenue", "TemporalCue",
             "Place", "AdminUnit", "CulturalFigure", "CommunityGroup"]
VOCAB = ["HeritageElement", "ActivityType", "CulturalArtifact", "CulturalConcept",
         "PracticeVenue", "RoleType", "TemporalCue", "HeritageDomain"]


def build_properties(g):
    """Trả về list dict mô tả property; domain/range có thể là tên, list (union) hoặc node."""
    cue_rng = lambda: union(g, *CUE_RANGE)
    P = []

    def op(name, dom, rng, vi, cvi, en, cen, sup=(), inv=None, chars=(), crmstr=NONE, opt=False):
        P.append(dict(kind="obj", name=name, dom=dom, rng=rng, vi=vi, cvi=cvi, en=en, cen=cen,
                      sup=list(sup), inv=inv, chars=list(chars), crm=crmstr, opt=opt))

    def dp(name, dom, rng, vi, cvi, en, cen, functional=False, crmstr=NONE):
        P.append(dict(kind="data", name=name, dom=dom, rng=rng, vi=vi, cvi=cvi, en=en, cen=cen,
                      chars=["Functional"] if functional else [], crm=crmstr, sup=[], inv=None, opt=False))

    # ---- cue ----
    op("hasCue", "CueBearer", cue_rng(), "có cue",
       "Cue tổng quát từ nút mang cue đến tín hiệu giúp nhận diện; super-property của các cue chuyên biệt. Non-simple vì là đầu ra của chain.",
       "has cue", "Generic cue from a cue bearer to a recognition signal; super-property of the specialised cue properties. Non-simple because it heads a chain.")
    op("hasDistinctiveCue", None, None, "có cue đặc trưng",
       "Cue được khai là đặc trưng của nút (độ đặc trưng thực tế do idf quyết định).",
       "has distinctive cue", "A cue declared distinctive for the node (actual distinctiveness is decided by idf).", sup=["hasCue"])
    op("typicallyIncludes", "HeritageElement", "ActivityType", "thường gồm",
       "Di sản thường gồm loại hoạt động này (type-level); nghịch đảo P150.",
       "typically includes", "The heritage typically includes this activity type (type level); inverse of P150.",
       sup=["hasCue"], crmstr=crm("nghịch đảo P150", "P150"))
    op("involvesRole", "HeritageElement", "RoleType", "liên quan vai trò",
       "Di sản thường có vai trò xã hội này (cue).", "involves role", "The heritage typically involves this social role (cue).",
       sup=["hasCue"], crmstr="custom (instance-level là PC14 qua Participation)")
    op("hasTemporalCue", "HeritageElement", "TemporalCue", "có cue thời gian",
       "Cue thời gian yếu (giờ, mùa).", "has temporal cue", "A weak temporal cue (time of day, season).", sup=["hasCue"])
    op("usedObjectOfType", ["HeritageElement", "ActivityType", "CulturalActivity", "Occurrence"], "CulturalArtifact",
       "dùng loại vật thể", "Loại hoạt động/di sản dùng loại vật phẩm này. Không phải sub-property của hasCue; cue suy ra qua chain typicallyIncludes ∘ usedObjectOfType.",
       "used object of type", "The activity/heritage uses this type of artifact. Not a sub-property of hasCue; the cue is derived via the chain typicallyIncludes ∘ usedObjectOfType.",
       crmstr=crm("P125 ở E7; ở E55 là shortcut tùy biến", "P125"))
    # ---- hai tầng đáp án ----
    op("realizesPractice", "ActivityType", "PracticeHeritage", "hiện thực hóa thực hành",
       "Nối loại hoạt động (cue đã link) với mục di sản thực hành tương ứng (tầng 1 của đáp án).",
       "realizes practice", "Links an activity type (the linked cue) to its practice heritage (tier-1 answer).", chars=["Functional"])
    op("featuredInEvent", "PracticeHeritage", "EventHeritage", "xuất hiện trong sự kiện",
       "Thực hành này thường xuất hiện trong sự kiện (suy ra từ chain; non-simple).",
       "featured in event", "This practice typically appears in the event (derived by chain; non-simple).")
    op("includesPractice", "EventHeritage", "PracticeHeritage", "bao gồm thực hành",
       "Nghịch đảo featuredInEvent; suy ra từ typicallyIncludes ∘ realizesPractice.",
       "includes practice", "Inverse of featuredInEvent; derived from typicallyIncludes ∘ realizesPractice.", inv="featuredInEvent")
    op("featuredInOccurrence", "PracticeHeritage", "Occurrence", "xuất hiện trong lần diễn ra",
       "(Optional) Thực hành được quan sát trong một lần diễn ra cụ thể.", "featured in occurrence",
       "(Optional) The practice was observed in one concrete occurrence.", opt=True)
    op("featuredIn", "PracticeHeritage", union(g, "EventHeritage", "Occurrence"), "xuất hiện trong",
       "Super-property của featuredInEvent và featuredInOccurrence.", "featured in",
       "Super-property of featuredInEvent and featuredInOccurrence.")
    op("hasActivityType", "CulturalActivity", "ActivityType", "có loại hoạt động",
       "(Optional) Phân loại instance hoạt động theo ActivityType.", "has activity type",
       "(Optional) Types a concrete activity with an ActivityType.", crmstr=crm("P2", "P2"), opt=True)
    op("consistsOf", union(g, "Occurrence", "CulturalActivity"), "CulturalActivity", "gồm",
       "(Optional) Lần diễn ra/hoạt động gồm các hoạt động con. Transitive nên non-simple.",
       "consists of", "(Optional) An occurrence/activity consists of sub-activities. Transitive, hence non-simple.",
       chars=["Transitive"], crmstr=crm("P9 (hai đầu cùng là E7 ⊂ E4)", "P9"), opt=True)
    # ---- Occurrence / không gian ----
    op("occurrenceOf", "Occurrence", "EventHeritage", "là lần diễn ra của", "Lần diễn ra thuộc về một EventHeritage.",
       "occurrence of", "The occurrence belongs to one EventHeritage.", inv="hasOccurrence", chars=["Functional"], crmstr=crm("P2", "P2"))
    op("hasOccurrence", None, None, "có lần diễn ra", "Nghịch đảo occurrenceOf.", "has occurrence", "Inverse of occurrenceOf.")
    op("tookPlaceAt", "Occurrence", "Place", "diễn ra tại", "Địa điểm diễn ra của một Occurrence.", "took place at",
       "Where an occurrence took place.", crmstr=crm("P7", "P7"))
    op("hasLocality", "CueBearer", "Place", "có địa phương",
       "Vùng không gian của nút (dùng cho kiểm GPS ở B4; decoy cũng cần để phân biệt theo place).",
       "has locality", "Spatial extent of the node (GPS check in B4; decoys need it to discriminate by place).",
       crmstr="custom (shortcut P7)")
    op("locatedWithin", "Place", "Place", "nằm trong", "Place nằm trong Place khác. Transitive.", "located within",
       "A place lies within another place. Transitive.", chars=["Transitive"], crmstr=crm("P89", "P89"))
    op("coversPlace", "AdminUnit", "Place", "bao phủ", "Đơn vị hành chính bao phủ một Place.", "covers place",
       "An admin unit covers a place.", crmstr=crm("~P7", "P7"))
    op("succeededBy", "AdminUnit", "AdminUnit", "được thay bởi", "Đơn vị hành chính kế nhiệm (sáp nhập/đổi tên).", "succeeded by",
       "Successor admin unit (merger/renaming).")
    # ---- nhận diện nhầm ----
    op("hasMember", "ConfusablePair", "CueBearer", "có thành viên", "Thành viên của cặp dễ nhầm.", "has member", "Member of a confusable pair.")
    op("confusableWith", "CueBearer", "CueBearer", "dễ nhầm với", "Hai nút dễ nhầm với nhau (đối xứng).", "confusable with",
       "Two nodes that are easily confused (symmetric).", chars=["Symmetric"])
    op("incompatibleCue", "CueBearer", cue_rng(), "cue loại trừ",
       "Cue mà nếu thấy thì loại nút này (chỉ có nghĩa khi khai tường minh, do OWA).", "incompatible cue",
       "A cue whose presence rules this node out (explicit only, due to OWA).")
    op("associatedWithEvent", "EventHeritage", "EventHeritage", "gắn với sự kiện",
       "Sự kiện này được tổ chức nhân dịp sự kiện kia nhưng không nằm trong nó (vd Hội đua bò Bảy Núi ↔ Sene Dolta).",
       "associated with event", "This event is held on the occasion of the other one but is not part of it.")
    op("veneratesFigure", "HeritageElement", "CulturalFigure", "tôn thờ / tưởng niệm",
       "Nhân vật văn hóa được thờ hoặc tưởng niệm trong di sản (Thần Nam Hải, Bà Chúa Xứ, Nguyễn Trung Trực...).",
       "venerates figure", "Cultural figure worshipped or commemorated by the heritage.")
    # ---- phân loại & mô tả ----
    op("hasDomain", "HeritageElement", "HeritageDomain", "thuộc lĩnh vực", "Lĩnh vực của di sản; nhiều giá trị, không disjoint.",
       "has domain", "Domain(s) of the heritage; multi-valued, not disjoint.", crmstr=crm("P2", "P2"))
    op("unescoDomain", None, "UnescoDomain", "lĩnh vực UNESCO", "Lĩnh vực theo Công ước UNESCO 2003.", "UNESCO domain",
       "Domain under the 2003 UNESCO Convention.", sup=["hasDomain"])
    op("vnCategory", None, "VnCategory", "loại hình theo pháp luật VN", "Loại hình theo pháp luật Việt Nam.", "Vietnamese category",
       "Category under Vietnamese law.", sup=["hasDomain"])
    op("hasTemporalRule", "EventHeritage", "TemporalRule", "có quy tắc thời gian", "Quy tắc thời gian chuẩn của sự kiện.",
       "has temporal rule", "The canonical calendar rule of the event.")
    op("hasPurpose", ["HeritageElement", "Occurrence", "CulturalActivity"], "Purpose", "có mục đích", "Mục đích của di sản/hoạt động.",
       "has purpose", "Purpose of the heritage/activity.", crmstr=crm("P21 (instance-level)", "P21"))
    op("hasSignificance", "HeritageElement", "Significance", "có ý nghĩa", "Ý nghĩa biểu tượng của di sản.", "has significance",
       "Symbolic meaning of the heritage.")
    op("hasBelief", "HeritageElement", "BeliefSystem", "gắn tín ngưỡng", "Hệ thống tín ngưỡng liên quan.", "has belief system",
       "Related belief system.")
    op("hasArtisticElement", "HeritageElement", "ArtisticElement", "có yếu tố nghệ thuật", "Yếu tố nghệ thuật của di sản.",
       "has artistic element", "Artistic element of the heritage.")
    op("bearerGroup", "HeritageElement", "CommunityGroup", "cộng đồng nắm giữ", "Cộng đồng nắm giữ di sản.", "bearer group",
       "Community that bears the heritage.")
    op("organizedBy", ["HeritageElement", "Occurrence"], "Organizer", "do ... tổ chức", "Đơn vị tổ chức.", "organized by",
       "Organising body.", crmstr=crm("~P14", "P14"))
    op("hasOriginStory", "HeritageElement", "OriginStory", "có sự tích", "Sự tích giải thích nguồn gốc.", "has origin story",
       "Origin narrative.", crmstr=crm("nghịch đảo P129", "P129"))
    op("broaderTerm", VOCAB, VOCAB, "khái niệm rộng hơn", "Quan hệ rộng-hẹp giữa các mục từ vựng (đàn kìm → đàn). Transitive.",
       "broader term", "Broader/narrower between vocabulary items. Transitive.", chars=["Transitive"], crmstr=crm("P127", "P127"))
    op("hasListing", "HeritageElement", "ListingEntry", "có mục Danh mục", "Mục Danh mục chứa di sản (CQ21).", "has listing entry",
       "Listing entry that contains the heritage (CQ21).")
    # ---- Participation (optional) ----
    op("agent", "Participation", "Agent", "tác nhân", "(Optional) Agent tham gia.", "agent", "(Optional) Participating agent.",
       crmstr=crm("PC14", "PC14"), opt=True)
    op("role", "Participation", "RoleType", "vai trò", "(Optional) Vai trò trong sự tham gia (P14.1).", "role",
       "(Optional) Role of the participation (P14.1).", crmstr=crm("PC14", "PC14"), opt=True)
    op("activity", "Participation", union(g, "Occurrence", "CulturalActivity"), "hoạt động",
       "(Optional) Activity (E7) mà agent tham gia.", "activity", "(Optional) The E7 activity the agent took part in.",
       crmstr=crm("PC14", "PC14"), opt=True)

    # ---- data properties ----
    dp("startDate", "Occurrence", XSD.dateTime, "ngày bắt đầu", "Ngày bắt đầu thực tế (xsd:dateTime vì xsd:date không thuộc OWL 2 datatype map; quy ước 00:00:00, chỉ phần ngày có nghĩa).", "start date", "Actual start date (xsd:dateTime because xsd:date is not in the OWL 2 datatype map; 00:00:00 by convention, only the date part is meaningful).",
       crmstr=crm("P4 → E52 → P82a", "P4", "E52", "P82a"))
    dp("endDate", "Occurrence", XSD.dateTime, "ngày kết thúc", "Ngày kết thúc thực tế, bao gồm cả ngày đó (00:00:00 theo quy ước; endDate ≥ startDate do SHACL/pipeline kiểm).",
       "end date", "Actual end date, inclusive (00:00:00 by convention; endDate ≥ startDate is checked by SHACL/pipeline).",
       crmstr=crm("P4 → E52 → P82b", "P4", "E52", "P82b"))
    dp("listingName", "HeritageElement", "PlainLiteral", "tên theo Danh mục", "Tên mục theo Danh mục, khác rdfs:label.",
       "listing name", "Name as in the list; distinct from rdfs:label.")
    dp("cueKind", union(g, *CUE_RANGE),
       data_enum(g, ["name", "datePlace", "object", "venue", "role", "activity", "temporal", "place"]),
       "loại cue", "Chỉ mã hóa LOẠI cue (để pipeline gán trọng số w_loại). Độ đặc trưng do idf và hasDistinctiveCue đảm nhận.",
       "cue kind", "Encodes only the KIND of cue (for the pipeline's w_kind). Distinctiveness is handled by idf and hasDistinctiveCue.",
       functional=True)
    dp("discriminatorKind", "ConfusablePair", XSD.string, "loại discriminator", "Chiều phân biệt: place, cue, temporal... (không functional).",
       "discriminator kind", "Discriminating dimension: place, cue, temporal... (not functional).")
    dp("discriminatorNote", "ConfusablePair", "PlainLiteral", "ghi chú discriminator", "Ghi chú cách phân biệt.", "discriminator note",
       "How to tell them apart.")
    dp("calendarSystem", "TemporalRule", data_enum(g, ["vn_lunar", "khmer_lunar", "solar"]), "hệ lịch",
       "Hệ lịch của rule. Quy ước đánh số tháng khmer_lunar: [chưa verify], chỉ khai enum. B4 chỉ so khi cùng hệ lịch.",
       "calendar system", "Calendar system of the rule. Month numbering for khmer_lunar: [chưa verify], enum only. B4 compares only within the same system.",
       functional=True)
    dp("monthStart", "TemporalRule", int_range(g, 1, 12), "tháng bắt đầu", "Tháng bắt đầu cửa sổ (1-12).", "start month",
       "Start month of the window (1-12).", functional=True)
    dp("monthEnd", "TemporalRule", int_range(g, 1, 12), "tháng kết thúc",
       "Tháng kết thúc cửa sổ; khác monthStart nếu vắt tháng (vd 29/8-1/9 âm).", "end month",
       "End month of the window; differs from monthStart when the window crosses months.", functional=True)
    dp("dayStart", "TemporalRule", int_range(g, 1, 31), "ngày bắt đầu (trong tháng)", "Ngày bắt đầu cửa sổ (1-31).",
       "start day", "Start day of the window (1-31).", functional=True)
    dp("dayEnd", "TemporalRule", int_range(g, 1, 31), "ngày kết thúc (trong tháng)", "Ngày kết thúc cửa sổ (1-31).",
       "end day", "End day of the window (1-31).", functional=True)
    dp("durationDays", "TemporalRule", XSD.positiveInteger, "số ngày kéo dài",
       "Chỉ dùng khi rule không có ngày cụ thể; dayStart/dayEnd ưu tiên khi có.", "duration (days)",
       "Used only when the rule has no concrete days; dayStart/dayEnd take precedence.", functional=True)
    dp("recurrence", "TemporalRule", XSD.string, "chu kỳ", "Chu kỳ lặp (vd annual).", "recurrence", "Recurrence (e.g. annual).",
       functional=True)
    dp("ruleStrength", "TemporalRule", data_enum(g, ["hard", "soft", "approx"]), "độ cứng của rule",
       "hard = nguồn ghi ngày cố định; soft = ngày thực tế dao động ±toleranceDays; approx = quy đổi từ hệ lịch khác (vd Khmer → âm Việt), có thể lệch ±toleranceMonths tháng. B4 chỉ trừ điểm nặng với hard.",
       "rule strength", "hard = fixed by source; soft = actual dates drift ±toleranceDays; approx = converted from another calendar, may shift ±toleranceMonths.",
       functional=True)
    dp("toleranceDays", "TemporalRule", XSD.nonNegativeInteger, "dung sai (ngày)", "Số ngày cho phép lệch quanh cửa sổ.",
       "tolerance (days)", "Allowed drift in days around the window.", functional=True)
    dp("toleranceMonths", "TemporalRule", int_range(g, 0, 2), "dung sai (tháng)",
       "Số tháng có thể lệch do khác hệ lịch (tháng nhuận Khmer vs Việt).", "tolerance (months)",
       "Months the window may shift because of calendar mismatch (leap months).", functional=True)
    dp("monthName", "TemporalRule", XSD.string, "tên tháng", "Tên tháng trong hệ lịch gốc khi chưa chốt cách đánh số (vd Kadeuk).",
       "month name", "Month name in the source calendar when numbering is not settled (e.g. Kadeuk).", functional=True)
    for nm, vi, en, hi in [("lunarStartMonth", "tháng âm bắt đầu", "lunar start month", 12), ("lunarStartDay", "ngày âm bắt đầu", "lunar start day", 30),
                           ("lunarEndMonth", "tháng âm kết thúc", "lunar end month", 12), ("lunarEndDay", "ngày âm kết thúc", "lunar end day", 30)]:
        dp(nm, "Occurrence", int_range(g, 1, hi), vi, "Ngày âm lịch Việt tương ứng của lần diễn ra (kiểm rule thời gian; bỏ trống nếu rơi vào tháng nhuận).",
           en, "Vietnamese lunar equivalent of the occurrence (for rule checks; empty for leap months).", functional=True)
    dp("registryStatus", "HeritageElement", data_enum(g, ["listed", "not_listed", "unverified"]), "trạng thái Danh mục",
       "listed = có mục Danh mục QG/UNESCO đã xác nhận; not_listed = đã tra, không thấy; unverified = có tin nhưng chưa đối chiếu được.",
       "registry status", "listed / not_listed / unverified.", functional=True)
    dp("validFrom", "AdminUnit", XSD.dateTime, "hiệu lực từ",
       "Mốc PHÁP LÝ bắt đầu hiệu lực. Mốc vận hành (nếu có nguồn) ghi bằng annotation ich:operationalNote.",
       "valid from", "LEGAL start of validity. The operational date (if sourced) goes in the annotation ich:operationalNote.",
       functional=True)
    dp("validTo", "AdminUnit", XSD.dateTime, "hiệu lực đến", "Mốc pháp lý kết thúc hiệu lực.", "valid to", "Legal end of validity.", functional=True)
    dp("adminLevel", "AdminUnit", XSD.string, "cấp hành chính", "Cấp hành chính (province, commune...).", "admin level",
       "Administrative level (province, commune...).", functional=True)
    dp("radiusKm", "Place", pos_decimal(g), "bán kính (km)", "Bán kính vùng quanh geometry điểm, dùng cho kiểm GPS (CQ14).",
       "radius (km)", "Radius around the point geometry, for the GPS check (CQ14).", functional=True)
    dp("listType", "ListingEntry", data_enum(g, ["QG", "UNESCO"]), "loại danh mục", "QG = Danh mục quốc gia; UNESCO.",
       "list type", "QG = national list; UNESCO.", functional=True)
    dp("decisionNumber", "ListingEntry", XSD.string, "số quyết định", "Số quyết định công bố.", "decision number",
       "Decision number.", functional=True)
    dp("decisionDate", "ListingEntry", XSD.dateTime, "ngày quyết định", "Ngày quyết định công bố.", "decision date",
       "Decision date.", functional=True)
    dp("sourceURL", "ListingEntry", XSD.anyURI, "URL nguồn", "URL nguồn của mục Danh mục.", "source URL", "Source URL of the entry.")
    return P


def resolve(g, x):
    """None | name | list(union) | node/URIRef/datatype -> node."""
    if x is None:
        return None
    if isinstance(x, (URIRef, BNode)):      # phải kiểm trước str: URIRef kế thừa str
        return x
    if isinstance(x, list):
        return union(g, *x)
    if x == "PlainLiteral":
        return URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#PlainLiteral")
    return ICH[x]


def build_tbox():
    g = Graph()
    for p, ns in [("ich", ICH), ("ex", EX), ("owl", OWL), ("rdfs", RDFS), ("xsd", XSD), ("skos", SKOS), ("geo", GEO)]:
        g.bind(p, ns)

    # Ontology header
    g.add((TBOX_IRI, RDF.type, OWL.Ontology))
    g.add((TBOX_IRI, RDFS.label, Literal("Ontology di sản văn hóa phi vật thể (TBox) phục vụ nhận diện ảnh/video", lang="vi")))
    g.add((TBOX_IRI, RDFS.label, Literal("Intangible cultural heritage ontology (TBox) for image/video recognition", lang="en")))
    g.add((TBOX_IRI, RDFS.comment, Literal(
        "Align CIDOC CRM 7.1.3 chỉ qua annotation ich:crmMapping (không import ECRM). Ghi [chưa verify] khi không có nguồn.", lang="vi")))
    g.add((TBOX_IRI, OWL.versionInfo, Literal("0.4 - namespace w3id; TemporalRule có ruleStrength/tolerance; ABox 20 di sản nạp từ CSV")))

    # Annotation properties
    for a in ["nerLabel", "crmMapping", "optional", "source", "verificationStatus", "operationalNote", "datasetId"]:
        g.add((ICH[a], RDF.type, OWL.AnnotationProperty))
    g.add((ICH.nerLabel, RDFS.comment, Literal("Nhãn NER gốc từ Khung thực thể.", lang="vi")))
    g.add((ICH.crmMapping, RDFS.comment, Literal("Ánh xạ tới CIDOC CRM 7.1.3 kèm URL; [chưa verify scope note] nếu chưa đối chiếu.", lang="vi")))
    g.add((ICH.optional, RDFS.comment, Literal("xsd:boolean; true = lớp/property instance-level không bắt buộc nhập liệu.", lang="vi")))
    g.add((ICH.source, RDFS.comment, Literal("URL nguồn của một individual (xsd:anyURI); không reify từng triple (CQ23).", lang="vi")))
    g.add((ICH.verificationStatus, RDFS.comment, Literal('Giá trị: "verified" | "unverified"; gắn trên individual (CQ23).', lang="vi")))
    g.add((ICH.operationalNote, RDFS.comment, Literal(
        "Ghi chú mốc VẬN HÀNH của AdminUnit, chỉ dùng khi có nguồn (validFrom là mốc pháp lý).", lang="vi")))
    g.add((ICH.datasetId, RDFS.comment, Literal("id dòng trong 20_di_san_verify.csv (truy vết nguồn dữ liệu).", lang="vi")))
    g.add((SKOS.altLabel, RDF.type, OWL.AnnotationProperty))
    for a, vi in [("altLabelNoDiacritics", "tên không dấu"), ("altLabelKhmerTranslit", "phiên âm Khmer"),
                  ("altLabelLocal", "tên địa phương"), ("altLabelListing", "tên theo Danh mục")]:
        g.add((ICH[a], RDF.type, OWL.AnnotationProperty))
        g.add((ICH[a], RDFS.subPropertyOf, SKOS.altLabel))
        g.add((ICH[a], RDFS.label, Literal(vi, lang="vi")))

    # GeoSPARQL tối thiểu
    g.add((GEO.Geometry, RDF.type, OWL.Class))
    g.add((GEO.hasGeometry, RDF.type, OWL.ObjectProperty))
    g.add((GEO.hasGeometry, RDFS.domain, ICH.Place))
    g.add((GEO.hasGeometry, RDFS.range, GEO.Geometry))
    g.add((GEO.hasGeometry, RDFS.comment, Literal("GeoSPARQL tối thiểu: Place → geo:Geometry (POINT) + ich:radiusKm.", lang="vi")))
    g.add((GEO.asWKT, RDF.type, OWL.DatatypeProperty))
    g.add((GEO.asWKT, RDF.type, OWL.FunctionalProperty))
    g.add((GEO.asWKT, RDFS.domain, GEO.Geometry))
    g.add((GEO.asWKT, RDFS.comment, Literal(
        "WKT POINT(lon lat). Mặc định range xsd:string để HermiT chạy được; dùng --wkt-typed để sinh geo:wktLiteral cho triple store.", lang="vi")))
    if WKT_TYPED:
        g.add((GEO.asWKT, RDFS.range, GEO.wktLiteral))
        g.add((GEO.wktLiteral, RDF.type, RDFS.Datatype))
    else:
        g.add((GEO.asWKT, RDFS.range, XSD.string))

    # Classes
    for (name, parent, ner, crmstr, vi_l, en_l, vi_c, en_c, optional) in CLASSES:
        c = ICH[name]
        g.add((c, RDF.type, OWL.Class))
        if parent:
            g.add((c, RDFS.subClassOf, ICH[parent]))
        annotate(g, c, vi_l, en_l, vi_c, en_c)
        for n in (ner or []):
            g.add((c, ICH.nerLabel, Literal(n)))
        g.add((c, ICH.crmMapping, Literal(crmstr)))
        if optional:
            g.add((c, ICH.optional, Literal(True)))

    # Properties
    for p in build_properties(g):
        node = ICH[p["name"]]
        g.add((node, RDF.type, OWL.ObjectProperty if p["kind"] == "obj" else OWL.DatatypeProperty))
        for ch in p["chars"]:
            g.add((node, RDF.type, getattr(OWL, ch + "Property")))
        d, r = resolve(g, p["dom"]), resolve(g, p["rng"])
        if d is not None:
            g.add((node, RDFS.domain, d))
        if r is not None:
            g.add((node, RDFS.range, r))
        for s in p["sup"]:
            g.add((node, RDFS.subPropertyOf, ICH[s]))
        if p["inv"]:
            g.add((node, OWL.inverseOf, ICH[p["inv"]]))
        annotate(g, node, p["vi"], p["en"], p["cvi"], p["cen"])
        g.add((node, ICH.crmMapping, Literal(p["crm"])))
        if p["opt"]:
            g.add((node, ICH.optional, Literal(True)))
    # hasOccurrence: domain/range lấy từ inverseOf (khai tường minh cho dễ đọc trong Protégé)
    g.add((ICH.hasOccurrence, RDFS.domain, ICH.EventHeritage))
    g.add((ICH.hasOccurrence, RDFS.range, ICH.Occurrence))
    # hasDistinctiveCue / unescoDomain / vnCategory: domain thừa hưởng từ super-property
    # (hasCue: CueBearer; hasDomain: HeritageElement) nên không khai lại.

    # Property chains (OWL 2 DL: RHS non-simple; regularity kiểm trong verify_ich.py)
    for parts, sup in [(["typicallyIncludes", "realizesPractice"], "includesPractice"),
                       (["typicallyIncludes", "usedObjectOfType"], "hasCue"),
                       (["featuredInOccurrence", "occurrenceOf"], "featuredInEvent")]:
        g.add((ICH[sup], OWL.propertyChainAxiom, lst(g, [ICH[x] for x in parts])))
    g.add((ICH.featuredInEvent, RDFS.subPropertyOf, ICH.featuredIn))
    g.add((ICH.featuredInOccurrence, RDFS.subPropertyOf, ICH.featuredIn))

    # Disjointness
    G1 = ["CueBearer", "HeritageDomain", "TemporalCue", "TemporalRule", "Occurrence", "Place", "AdminUnit", "Agent",
          "RoleType", "Participation", "ActivityType", "PracticeVenue", "CulturalArtifact", "CulturalConcept",
          "ConfusablePair", "ListingEntry"]
    all_disjoint(g, G1 + [GEO.Geometry])
    for c in G1:                      # CulturalActivity (E7 instance): disjoint với tất cả, trừ Occurrence (cùng E7)
        if c != "Occurrence":
            pair_disjoint(g, "CulturalActivity", c)
    pair_disjoint(g, "CulturalActivity", GEO.Geometry)
    for c in G1:                      # CulturalFigure: disjoint, trừ Agent (một Person có thể là HistoricalFigure)
        if c != "Agent":
            pair_disjoint(g, "CulturalFigure", c)
    pair_disjoint(g, "CulturalFigure", GEO.Geometry)
    pair_disjoint(g, "HeritageElement", "LookalikeElement")
    pair_disjoint(g, "EventHeritage", "PracticeHeritage")
    pair_disjoint(g, "UnescoDomain", "VnCategory")
    pair_disjoint(g, "Person", "Group")
    pair_disjoint(g, "CommunityGroup", "Organization")
    pair_disjoint(g, "Significance", "Purpose")

    # Cardinality (chỉ trên property simple)
    def sub(c, r):
        g.add((ICH[c], RDFS.subClassOf, r))
    sub("Occurrence", restr(g, "occurrenceOf", "exact", 1))
    sub("Occurrence", restr(g, "startDate", "exact", 1))
    sub("Occurrence", restr(g, "endDate", "exact", 1))
    sub("Occurrence", restr(g, "tookPlaceAt", "min", 1))
    sub("PracticeHeritage", restr(g, "hasTemporalRule", "max", 0))
    sub("EventHeritage", restr(g, "hasTemporalRule", "min", 1))
    sub("TemporalRule", restr(g, "calendarSystem", "min", 1))
    for pr in ["agent", "role", "activity"]:
        sub("Participation", restr(g, pr, "exact", 1))

    # 5 individual UNESCO (D6) + AllDifferent (OWL không có UNA)
    domains = [("OralTraditionsExpressions", "Các truyền thống và biểu đạt truyền khẩu", "Oral traditions and expressions"),
               ("PerformingArts", "Nghệ thuật trình diễn", "Performing arts"),
               ("SocialPracticesRitualsFestive", "Tập quán xã hội, tín ngưỡng và các lễ hội", "Social practices, rituals and festive events"),
               ("KnowledgeNatureUniverse", "Tri thức và tập quán liên quan đến tự nhiên và vũ trụ", "Knowledge and practices concerning nature and the universe"),
               ("TraditionalCraftsmanship", "Nghề thủ công truyền thống", "Traditional craftsmanship")]
    for n, vi, en in domains:
        d = ICH[n]
        g.add((d, RDF.type, OWL.NamedIndividual))
        g.add((d, RDF.type, ICH.UnescoDomain))
        g.add((d, RDFS.label, Literal(vi, lang="vi")))
        g.add((d, RDFS.label, Literal(en, lang="en")))
        g.add((d, ICH.source, Literal(UNESCO_PDF, datatype=XSD.anyURI)))
        g.add((d, ICH.verificationStatus, Literal("verified")))
    ad = BNode()
    g.add((ad, RDF.type, OWL.AllDifferent))
    g.add((ad, OWL.distinctMembers, lst(g, [ICH[n] for n, _, _ in domains])))
    return g


# --------------------------------------------------------------------------
# ABox test
# --------------------------------------------------------------------------
def build_abox():
    g = Graph()
    for p, ns in [("ich", ICH), ("ex", EX), ("owl", OWL), ("rdfs", RDFS), ("xsd", XSD), ("skos", SKOS), ("geo", GEO)]:
        g.bind(p, ns)
    g.add((ABOX_IRI, RDF.type, OWL.Ontology))
    g.add((ABOX_IRI, OWL.imports, TBOX_IRI))
    g.add((ABOX_IRI, RDFS.comment, Literal(
        "ABox kiểm thử. Quy ước: individual từ vựng (loại hoạt động, vật phẩm, vai trò...) dùng tiền tố ich:, "
        "di sản/địa điểm/lần diễn ra dùng ex:. Mọi dữ kiện đều unverified trừ khi ghi khác; tọa độ chỉ xấp xỉ minh họa.", lang="vi")))

    def ind(iri, classes, vi=None, status="unverified", source=None, comment=None):
        s = iri
        g.add((s, RDF.type, OWL.NamedIndividual))
        for c in ([classes] if not isinstance(classes, list) else classes):
            g.add((s, RDF.type, c))
        if vi:
            g.add((s, RDFS.label, Literal(vi, lang="vi")))
        g.add((s, ICH.verificationStatus, Literal(status)))
        if source:
            g.add((s, ICH.source, Literal(source, datatype=XSD.anyURI)))
        if comment:
            g.add((s, RDFS.comment, Literal(comment, lang="vi")))
        return s

    def kind(s, k):
        g.add((s, ICH.cueKind, Literal(k)))

    def alt(s, noacc=None, khmer=None, local=None, listing=None):
        if noacc:
            g.add((s, ICH.altLabelNoDiacritics, Literal(noacc)))
        if khmer:
            g.add((s, ICH.altLabelKhmerTranslit, Literal(khmer)))
        if local:
            g.add((s, ICH.altLabelLocal, Literal(local, lang="vi")))
        if listing:
            g.add((s, ICH.altLabelListing, Literal(listing, lang="vi")))

    def add(s, p, *objs):
        for o in objs:
            g.add((s, p, o))

    # ---------------- Từ vựng (ich:) ----------------
    # Activity types
    for iri, cls, vi in [(ICH.LeCungTrang, ICH.Ritual, "Lễ cúng trăng"), (ICH.DuaGheNgo, ICH.SocialPractice, "Đua ghe Ngo"),
                         (ICH.ThaDenNuoc, ICH.Ritual, "Thả đèn nước"), (ICH.MuaRomVong, ICH.Performance, "Múa Rom vong"),
                         (ICH.DapNuiCat, ICH.SocialPractice, "Đắp núi cát"), (ICH.LeTamPhat, ICH.Ritual, "Lễ tắm Phật"),
                         (ICH.DungCayBeo, ICH.SocialPractice, "Dựng cây bẹo"), (ICH.BuonBanTrenSong, ICH.SocialPractice, "Buôn bán trên sông")]:
        ind(iri, cls, vi)
        kind(iri, "activity")
    g.add((ICH.ThaDenNuoc, RDFS.comment, Literal("Phân loại Ritual là đề xuất, khung gốc chưa liệt kê.", lang="vi")))
    alt(ICH.MuaRomVong, noacc="Mua Rom vong", khmer="Rom Vong")
    alt(ICH.DapNuiCat, noacc="Dap nui cat", khmer="Puôn Phnum Khsách")
    # Artifacts
    for iri, cls, vi in [(ICH.GheNgo, ICH.VehicleVessel, "Ghe Ngo"), (ICH.ComDep, ICH.Offering, "Cốm dẹp"),
                         (ICH.TrangPhucKhmer, ICH.Costume, "Trang phục Khmer"), (ICH.CayBeo, ICH.ToolEquipment, "Cây bẹo"),
                         (ICH.GheThuongHo, ICH.VehicleVessel, "Ghe thương hồ")]:
        ind(iri, cls, vi)
        kind(iri, "object")
    alt(ICH.GheThuongHo, noacc="Ghe thuong ho", local="ghe hàng")
    g.add((ICH.GheThuongHo, RDFS.comment, Literal('Tên "ghe hàng" chưa tìm thấy như thuật ngữ: [chưa verify].', lang="vi")))
    alt(ICH.GheNgo, noacc="Ghe Ngo")
    alt(ICH.CayBeo, noacc="Cay beo")
    # Roles / venue / temporal
    ind(ICH.ConDam, ICH.RoleType, "Con dầm"); kind(ICH.ConDam, "role"); alt(ICH.ConDam, noacc="Con dam")
    ind(ICH.ThuongHo, ICH.RoleType, "Thương hồ"); kind(ICH.ThuongHo, "role"); alt(ICH.ThuongHo, noacc="Thuong ho")
    ind(ICH.MatSongDongGhe, ICH.PracticeVenue, "Mặt sông đông ghe xuồng"); kind(ICH.MatSongDongGhe, "venue")
    ind(ICH.SangSom, ICH.TemporalCue, "Sáng sớm"); kind(ICH.SangSom, "temporal")
    # Phân loại pháp luật VN (chưa verify)
    ind(ICH.LeHoiTruyenThong, ICH.VnCategory, "Lễ hội truyền thống")
    ind(ICH.TapQuanXaHoiVaTinNguong, ICH.VnCategory, "Tập quán xã hội và tín ngưỡng")
    # usedObjectOfType (type-level)
    add(ICH.DuaGheNgo, ICH.usedObjectOfType, ICH.GheNgo)
    add(ICH.LeCungTrang, ICH.usedObjectOfType, ICH.ComDep)
    add(ICH.DungCayBeo, ICH.usedObjectOfType, ICH.CayBeo)

    # ---------------- Địa điểm / hành chính ----------------
    songMaspero = ind(EX.SongMaspero_CauQuay_CauCao, ICH.NaturalFeature, "Sông Maspéro (đoạn Cầu Quay - Cầu Cao)")
    placeSoc = ind(EX.Place_SocTrangArea, ICH.Place, "Vùng Sóc Trăng")
    placeCanTho = ind(EX.Place_CanThoNewArea, ICH.Place, "Vùng Cần Thơ (sau sáp nhập)")
    songCanTho = ind(EX.SongCanTho, ICH.NaturalFeature, "Sông Cần Thơ"); kind(songCanTho, "place")
    alt(songCanTho, noacc="Song Can Tho")
    placeCaiRang = ind(EX.Place_ChoNoiCaiRang, ICH.Place, "Vùng chợ nổi Cái Răng")
    for iri, vi in [(EX.Place_PhongDien, "Vùng Phong Điền"), (EX.Place_NgaBay, "Vùng Ngã Bảy"), (EX.Place_CaiBe, "Vùng Cái Bè")]:
        ind(iri, ICH.Place, vi)
    add(songMaspero, ICH.locatedWithin, placeSoc)
    add(placeSoc, ICH.locatedWithin, placeCanTho)
    add(placeCaiRang, ICH.locatedWithin, EX.Place_CanThoOldArea, songCanTho)   # Place_CanThoOldArea do abox_registry tạo
    # Geometry (GeoSPARQL tối thiểu) - TỌA ĐỘ XẤP XỈ MINH HỌA, CHƯA VERIFY
    for place, gid, wkt, rad in [(songMaspero, EX.Geom_SongMaspero, "POINT(105.9715 9.6030)", "1.0"),
                                 (placeCaiRang, EX.Geom_ChoNoiCaiRang, "POINT(105.7925 10.0067)", "2.0")]:
        add(place, GEO.hasGeometry, gid)
        g.add((gid, RDF.type, GEO.Geometry))
        g.add((gid, GEO.asWKT, Literal(wkt, datatype=GEO.wktLiteral) if WKT_TYPED else Literal(wkt)))
        g.add((place, ICH.radiusKm, Literal(rad, datatype=XSD.decimal)))
        g.add((gid, RDFS.comment, Literal("Tọa độ xấp xỉ minh họa cho test, [chưa verify].", lang="vi")))
        g.add((gid, ICH.verificationStatus, Literal("unverified")))
    # AdminUnit (D7): validFrom = mốc pháp lý (NQ 202/2025/QH15, Prompt 1 #7); mốc vận hành 1/7/2025 [chưa verify]
    adminSoc = ind(EX.Admin_SocTrang_pre2025, ICH.AdminUnit, "Tỉnh Sóc Trăng")
    adminCT = ind(EX.Admin_TPCanTho_2025, ICH.AdminUnit, "Thành phố Cần Thơ (sau sáp nhập)",
                  comment="Mốc vận hành 1/7/2025: [chưa verify], nên chưa ghi ich:operationalNote.")
    for a in (adminSoc, adminCT):
        g.add((a, ICH.adminLevel, Literal("province")))
    add(adminSoc, ICH.coversPlace, placeSoc)
    g.add((adminSoc, ICH.validTo, Literal("2025-06-11T00:00:00", datatype=XSD.dateTime)))
    add(adminSoc, ICH.succeededBy, adminCT)
    add(adminCT, ICH.coversPlace, placeCanTho)
    g.add((adminCT, ICH.validFrom, Literal("2025-06-12T00:00:00", datatype=XSD.dateTime)))

    # ---------------- Cụm 1: Oóc Om Bóc Sóc Trăng (+ 2 EventHeritage đối chứng) ----------------
    ooc = ind(EX.OocOmBocSocTrang, ICH.EventHeritage, "Oóc Om Bóc Sóc Trăng")
    g.add((ooc, ICH.listingName, Literal("Lễ hội Đua ghe Ngo của người Khmer tỉnh Sóc Trăng", lang="vi")))
    alt(ooc, noacc="Ooc Om Boc Soc Trang", khmer="Ok Om Bok", local="Lễ hội Cúng Trăng",
        listing="Lễ hội Đua ghe Ngo của người Khmer tỉnh Sóc Trăng")
    add(ooc, ICH.unescoDomain, ICH.SocialPracticesRitualsFestive)
    add(ooc, ICH.vnCategory, ICH.LeHoiTruyenThong)
    add(ooc, ICH.hasLocality, songMaspero)
    add(ooc, ICH.typicallyIncludes, ICH.LeCungTrang, ICH.DuaGheNgo, ICH.ThaDenNuoc, ICH.MuaRomVong)
    add(ooc, ICH.involvesRole, ICH.ConDam)
    add(ooc, ICH.hasDistinctiveCue, ICH.GheNgo)
    add(ooc, ICH.hasCue, ICH.TrangPhucKhmer)
    sig = ind(EX.Sig_TaOnMatTrang, ICH.Significance, "Tạ ơn Mặt Trăng")
    khmer = ind(EX.DongBaoKhmer, ICH.CommunityGroup, "Đồng bào Khmer")
    add(ooc, ICH.hasSignificance, sig)
    add(ooc, ICH.bearerGroup, khmer)
    # TemporalRule, Occurrence, ListingEntry của cả 20 di sản: abox_registry.py (nạp từ CSV)

    occ = EX.OocOmBocSocTrang_2024   # Occurrence do abox_registry tạo từ CSV
    # optional extension
    duaAct = ind(EX.DuaGheNgo_SocTrang_2024, ICH.CulturalActivity, "Đua ghe Ngo Sóc Trăng 2024")
    add(duaAct, ICH.hasActivityType, ICH.DuaGheNgo)
    add(occ, ICH.consistsOf, duaAct)
    agent1 = ind(EX.Agent_001, ICH.Person, "Agent minh họa", comment="Minh họa, không phải dữ kiện.")
    part = ind(EX.Part_001, ICH.Participation)
    add(part, ICH.agent, agent1)
    add(part, ICH.role, ICH.ConDam)
    add(part, ICH.activity, duaAct)

    romH = ind(EX.MuaRomVong_Heritage, ICH.PracticeHeritage, "Múa Rom vong")
    g.add((romH, ICH.listingName, Literal("Múa Rom vong", lang="vi")))
    alt(romH, noacc="Mua Rom vong", khmer="Rom Vong")
    add(romH, ICH.unescoDomain, ICH.PerformingArts)
    add(ICH.MuaRomVong, ICH.realizesPractice, romH)
    add(romH, ICH.featuredInOccurrence, occ)   # kiểm chain featuredInOccurrence ∘ occurrenceOf

    chol = ind(EX.CholChnamThmay, ICH.EventHeritage, "Tết Chôl Chnăm Thmây",
               comment="Đối chứng với Oóc Om Bóc (ứng viên B trong khung gốc).")
    alt(chol, noacc="Tet Chol Chnam Thmay")
    add(chol, ICH.unescoDomain, ICH.SocialPracticesRitualsFestive)
    add(chol, ICH.typicallyIncludes, ICH.DapNuiCat, ICH.LeTamPhat, ICH.MuaRomVong)
    add(chol, ICH.hasCue, ICH.TrangPhucKhmer)

    sene = ind(EX.SeneDolta, ICH.EventHeritage, "Lễ Sene Dolta")
    alt(sene, noacc="Sene Dolta")

    pA1 = ind(EX.Pair_A1, ICH.ConfusablePair)
    add(pA1, ICH.hasMember, ooc, chol)
    g.add((pA1, ICH.discriminatorKind, Literal("cue")))
    g.add((pA1, ICH.discriminatorKind, Literal("temporal")))
    g.add((pA1, ICH.discriminatorNote, Literal(
        "Cùng Khmer, cùng trang phục; phân biệt bằng ghe Ngo/thả đèn nước (Oóc Om Bóc) vs núi cát/tắm Phật (Chôl Chnăm Thmây) và hệ lịch.", lang="vi")))

    # ---------------- Cụm 2: Văn hóa chợ nổi Cái Răng + decoy ----------------
    cr = ind(EX.ChoNoiCaiRang, ICH.PracticeHeritage, "Văn hóa chợ nổi Cái Răng")
    g.add((cr, ICH.listingName, Literal("Văn hóa chợ nổi Cái Răng", lang="vi")))
    alt(cr, noacc="Cho noi Cai Rang", listing="Văn hóa chợ nổi Cái Răng")
    add(cr, ICH.unescoDomain, ICH.SocialPracticesRitualsFestive)       # ánh xạ của tôi
    add(cr, ICH.vnCategory, ICH.TapQuanXaHoiVaTinNguong)               # [chưa verify mục Danh mục]
    add(cr, ICH.hasLocality, placeCaiRang)
    add(cr, ICH.hasCue, ICH.CayBeo, ICH.GheThuongHo, songCanTho)
    add(cr, ICH.hasDistinctiveCue, ICH.MatSongDongGhe)
    add(cr, ICH.hasTemporalCue, ICH.SangSom)
    add(cr, ICH.involvesRole, ICH.ThuongHo)
    add(cr, ICH.typicallyIncludes, ICH.DungCayBeo, ICH.BuonBanTrenSong)

    decoys = [(EX.ChoNoiPhongDien, "Chợ nổi Phong Điền", EX.Place_PhongDien, [ICH.CayBeo, ICH.GheThuongHo, songCanTho]),
              (EX.ChoNoiNgaBay, "Chợ nổi Ngã Bảy", EX.Place_NgaBay, [ICH.CayBeo, ICH.GheThuongHo]),
              (EX.ChoNoiCaiBe, "Chợ nổi Cái Bè", EX.Place_CaiBe, [ICH.CayBeo, ICH.GheThuongHo])]
    for iri, vi, pl, cues in decoys:
        d = ind(iri, ICH.LookalikeElement, vi)
        add(d, ICH.hasLocality, pl)
        add(d, ICH.hasCue, *cues)
        add(cr, ICH.confusableWith, d)
    for pid, dec, kinds, note in [
        (EX.Pair_B1, EX.ChoNoiPhongDien, ["place", "cue"],
         "Cùng trên sông Cần Thơ, cùng cây bẹo; phân biệt bằng vị trí (GPS/OCR). Phong Điền thưa ghe hơn (yếu, tương đối, chưa có ngưỡng)."),
        (EX.Pair_B2, EX.ChoNoiNgaBay, ["place"], "Cùng cue chung; chỉ phân biệt bằng vị trí."),
        (EX.Pair_B3, EX.ChoNoiCaiBe, ["place"], "Sông Tiền vs sông Cần Thơ (OCR/GPS).")]:
        p = ind(pid, ICH.ConfusablePair)
        add(p, ICH.hasMember, cr, dec)
        for k in kinds:
            g.add((p, ICH.discriminatorKind, Literal(k)))
        g.add((p, ICH.discriminatorNote, Literal(note, lang="vi")))

    # ---------------- 20 di sản từ CSV ----------------
    import abox_registry
    abox_registry.build(g, ind, add, kind, alt, CSV_DIR)
    return g


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = Path(args[0] if args else ".")
    out.mkdir(parents=True, exist_ok=True)
    tb, ab = build_tbox(), build_abox()
    tb.serialize(out / "ich-tbox.ttl", format="turtle")
    ab.serialize(out / "ich-abox.ttl", format="turtle")
    # catalog cho Protégé: owl:imports <TBOX_IRI> -> ich-tbox.ttl (mở ABox mà không cần mạng)
    (out / "catalog-v001.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        '<catalog prefer="public" xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">\n'
        f'    <uri name="{TBOX_IRI}" uri="ich-tbox.ttl"/>\n'
        '</catalog>\n', encoding="utf-8")
    # Bản gộp một file (RDF/XML) để mở thẳng trong Protégé, không phụ thuộc owl:imports/catalog
    full = Graph()
    for p, ns in [("ich", ICH), ("ex", EX), ("owl", OWL), ("rdfs", RDFS), ("xsd", XSD), ("skos", SKOS), ("geo", GEO)]:
        full.bind(p, ns)
    FULL_IRI = URIRef(str(TBOX_IRI) + "/full")
    full.add((FULL_IRI, RDF.type, OWL.Ontology))
    full.add((FULL_IRI, RDFS.label, Literal("ICH Mekong - TBox + ABox gộp (để xem đồ thị trong Protégé)", lang="vi")))
    for gg in (tb, ab):
        for t in gg:
            if t[0] in (TBOX_IRI, ABOX_IRI) and t[1] in (RDF.type, OWL.imports, RDFS.label, RDFS.comment, OWL.versionInfo):
                continue
            full.add(t)
    full.serialize(out / "ich-full.owl", format="xml")
    print(f"ich-tbox.ttl: {len(tb)} | ich-abox.ttl: {len(ab)} | ich-full.owl: {len(full)} triples -> {out.resolve()}")


if __name__ == "__main__":
    main()
