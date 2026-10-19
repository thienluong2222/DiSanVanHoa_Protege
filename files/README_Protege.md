# ICH Mekong ontology v0.4 – mở và xem đồ thị tri thức trong Protégé 5.6

Namespace: TBox `https://w3id.org/ich-mekong/ontology#` (prefix `ich:`), dữ liệu `https://w3id.org/ich-mekong/data#` (prefix `ex:`).
IRI w3id chưa đăng ký redirect, Protégé không cần resolve vì mọi thứ đều có file local.

## Các file
| File | Nội dung |
|---|---|
| `ich-full.owl` | **TBox + ABox gộp (RDF/XML). Mở file này để xem đồ thị**, không phụ thuộc import |
| `ich-tbox.ttl` | Chỉ TBox (class, property, ràng buộc) |
| `ich-abox.ttl` + `catalog-v001.xml` | ABox (import TBox qua catalog). Dùng khi muốn sửa riêng dữ liệu |
| `gen_ich_owl.py` + `abox_registry.py` | Sinh 3 file trên từ 2 CSV: `python3 gen_ich_owl.py out/` (CSV đặt cùng thư mục script) |
| `verify_ich.py` | Kiểm toàn bộ: `python3 verify_ich.py out/` (cần `pip install rdflib owlready2`, Java 11+) |

## Xem đồ thị
1. **File → Open…** chọn `ich-full.owl`.
2. Hiện tên tiếng Việt thay vì IRI: **View → Render by label (rdfs:label)**. Nếu vẫn hiện tiếng Anh/IRI: **File → Preferences → Renderer**, thêm `vi` lên đầu danh sách ngôn ngữ annotation.
3. **Window → Tabs → OntoGraf** (OntoGraf có sẵn trong bản Protégé 5.x desktop; nếu không thấy: File → Check for plugins).
   - Kéo một class (vd `EventHeritage`) từ cây bên trái vào canvas, double-click node để bung các individual.
   - Double-click một individual (vd *Lễ hội Ok Om Bok Trà Vinh*) để bung các cạnh `typicallyIncludes`, `hasLocality`, `hasTemporalRule`, `hasListing`, `confusableWith`…
   - Thanh **Arc Types** bên phải: tắt `has subclass`/`has individual` khi chỉ muốn xem quan hệ giữa các individual.
   - OntoGraf chỉ vẽ assertion **có sẵn trong file**; các quan hệ suy ra (chain `includesPractice`, `featuredInEvent`, transitive `locatedWithin`) xem ở tab Individuals sau khi chạy reasoner.
4. Cách đi gợi ý để demo: `Văn hóa chợ nổi Cái Răng` → 3 decoy (`confusableWith`) → `Lễ hội Oóc Om Bóc Sóc Trăng` → `Múa Rom vong` → `Tết Chôl Chnăm Thmây`.

## Chạy reasoner
**Reasoner → HermiT → Start reasoner**. Không có popup "inconsistent" là đạt (đã kiểm bằng HermiT CLI trên `ich-full.owl`).
Sau đó tab **Individuals by class**, chọn individual, bật **Show inferences**.

| Kiểm | Kỳ vọng |
|---|---|
| Active ontology → Metrics | ~49 class (có `geo:Geometry`), 42 object property, 31 data property, 193 individual (đếm bằng OWLAPI) |
| Individual `Lễ hội Oóc Om Bóc Sóc Trăng` | `hasCue` (suy ra) có ghe Ngo, cốm dẹp…; `includesPractice` = Múa Rom vong |
| Individual `Lễ hội Ok Om Bok Trà Vinh` | `hasCue` (suy ra qua chain) có Ghe Ngo, Cốm dẹp |
| DL Query `HeritageElement and (hasCue value GheNgo)` | Oóc Om Bóc Sóc Trăng, Ok Om Bok Trà Vinh |
| DL Query `EventHeritage and (veneratesFigure value ThanNamHai)` | Nghinh Ông Trần Đề, Nghinh Ông Sông Đốc |
| DL Query `LookalikeElement` | 3 chợ nổi decoy |
| DL Query `HeritageElement and (registryStatus value "not_listed")` | Chôl Chnăm Thmây, Sene Dolta |

Các DL Query suy ra từ entailment đã kiểm bằng HermiT/OWLAPI (xem `verify_report.txt`), **chưa chạy thử trong giao diện Protégé**. Khi gõ trong DL Query tab dùng tên ngắn (Protégé tự gắn prefix) hoặc nhãn nếu đang render by label.

## SPARQL (tab SPARQL Query) – ví dụ
```sparql
PREFIX ich: <https://w3id.org/ich-mekong/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?heritage ?year ?start ?lm ?ld WHERE {
  ?o ich:occurrenceOf ?h ; ich:startDate ?start .
  ?h rdfs:label ?heritage . ?o rdfs:label ?year .
  OPTIONAL { ?o ich:lunarStartMonth ?lm ; ich:lunarStartDay ?ld }
} ORDER BY ?heritage ?start
```

## Thay đổi so với v0.3
- Namespace `example.org` → `w3id.org/ich-mekong`. ABox đổi tên `ich-test-abox.ttl` → `ich-abox.ttl`.
- `TemporalRule` thêm `ruleStrength` (hard/soft/approx), `toleranceDays`, `toleranceMonths`, `monthName`. Lễ Khmer (Oóc Om Bóc, Ok Om Bok, Sene Dolta) có 2 rule: rule `khmer_lunar` gốc (chỉ `monthName`, chưa chốt số tháng) + rule `vn_lunar` approx, `toleranceMonths = 1`.
- `Occurrence` thêm `lunarStartMonth/Day`, `lunarEndMonth/Day`. `HeritageElement` thêm `registryStatus`. Object property mới: `associatedWithEvent`, `veneratesFigure`. Annotation `datasetId` = id dòng CSV.
- ABox: 20 di sản, 21 occurrence (2023–2025), 19 ListingEntry QG + 2 UNESCO, 4 cặp dễ nhầm mới, hành chính cấp tỉnh trước/sau sáp nhập 2025.

## Lưu ý
- HermiT chỉ nhận datatype trong OWL 2 datatype map: ngày dùng `xsd:dateTime`, `geo:asWKT` là `xsd:string`. Bản `geo:wktLiteral` cho triple store: `python3 gen_ich_owl.py out --wkt-typed` (reasoner sẽ báo lỗi datatype).
- Văn bản free-text của CSV (time_rule, occ, notes) nằm trong `rdfs:comment`; trường cấu trúc là bảng curated trong `abox_registry.py`. Sửa CSV mà không sửa bảng curated thì chỉ comment/nguồn thay đổi.
