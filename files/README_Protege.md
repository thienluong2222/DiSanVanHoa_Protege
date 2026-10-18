# Mở và kiểm ontology ICH trong Protégé 5.6

## Mở file
1. Để `ich-tbox.ttl`, `ich-test-abox.ttl`, `catalog-v001.xml` chung một thư mục.
2. **File → Open…** chọn `ich-tbox.ttl` (IRI `https://example.org/ich`). Muốn xem cả dữ liệu mẫu thì mở `ich-test-abox.ttl`; `owl:imports` được phân giải về file local nhờ `catalog-v001.xml`.
3. Namespace `example.org` là placeholder, đổi ở `ICH`/`EX` trong `gen_ich_owl.py` rồi sinh lại.

## Chạy HermiT
**Reasoner → HermiT → Start reasoner** (nên mở ABox để có individual). Không có popup "inconsistent" là đạt. Nếu có: **Reasoner → Explain inconsistent ontology**.

## Các tab cần kiểm
| Tab | Kiểm gì | Kỳ vọng |
|---|---|---|
| Active ontology | Metrics, Imports (khi mở ABox) | 48 class (gồm `geo:Geometry`), 40 object property, 22 data property; import `https://example.org/ich` |
| Classes | Class hierarchy (inferred), nhánh `owl:Nothing` | Không class nào bị gạch đỏ; `CueBearer` có 2 con `HeritageElement`, `LookalikeElement` |
| Classes → Disjoint With | `HeritageElement` | `LookalikeElement`, `HeritageDomain`, `TemporalCue`, `ActivityType`... |
| Object properties | Characteristics + "SubProperty Of (Chain)" | `hasCue`, `includesPractice`, `featuredInEvent` có chain; `consistsOf`, `broaderTerm`, `locatedWithin` Transitive; `confusableWith` Symmetric; `occurrenceOf`, `realizesPractice` Functional |
| Data properties | Range của `cueKind`, `calendarSystem`, `monthStart` | Enum 8 giá trị / enum 3 giá trị / integer 1..12 |
| Individuals | Chọn `OocOmBocSocTrang`, bật **Show inferences** | `hasCue` có `GheNgo`, `ComDep`...; `includesPractice` = `MuaRomVong_Heritage` |
| DL Query | `HeritageElement and (hasCue value GheNgo)` | `OocOmBocSocTrang` |
| DL Query | `includesPractice value MuaRomVong_Heritage` | `OocOmBocSocTrang`, `CholChnamThmay` |
| DL Query | `LookalikeElement` | 3 chợ nổi decoy |

Các truy vấn DL ở trên suy ra từ kết quả entailment đã kiểm bằng HermiT (xem `verify_report.txt`); chưa chạy thử trong giao diện Protégé.

## Lưu ý
- HermiT chỉ nhận datatype trong OWL 2 datatype map: vì vậy ngày dùng `xsd:dateTime` (không phải `xsd:date`), và `geo:asWKT` là `xsd:string`. Muốn `geo:wktLiteral` đúng chuẩn GeoSPARQL cho triple store: `python3 gen_ich_owl.py out --wkt-typed` (reasoner sẽ báo lỗi datatype với bản này).
- Sinh lại: `python3 gen_ich_owl.py out/`. Kiểm lại toàn bộ: `python3 verify_ich.py out/` (cần `pip install rdflib owlready2`, Java 11+).
