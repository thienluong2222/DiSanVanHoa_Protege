# ICH Mekong Ontology (v0.4)

Ontology và đồ thị tri thức (Knowledge Graph) phục vụ mô hình hóa, bảo tồn và hỗ trợ nhận diện, suy luận ngữ nghĩa cho **20 Di sản Văn hóa Phi vật thể (ICH)** tiêu biểu tại khu vực Đồng bằng sông Cửu Long (ĐBSCL).

- **Chuẩn biểu diễn:** OWL 2 DL Profile.
- **Công cụ hỗ trợ:** Protégé 5.6+, HermiT Reasoner, RDFLib, Owlready2.
- **Ánh xạ chuẩn quốc tế:** CIDOC CRM 7.1.3 (thông qua annotation `ich:crmMapping`).
- **Namespace:**
  - TBox (Lược đồ ontology): `https://w3id.org/ich-mekong/ontology#` (prefix `ich:`)
  - ABox (Dữ liệu cá thể): `https://w3id.org/ich-mekong/data#` (prefix `ex:`)

---


```text
├── 20_di_san/
│   ├── 20_di_san_verify.csv               # Dữ liệu 20 di sản đã xác thực (QĐ công nhận, loại hình, địa điểm, hệ lịch)
│   └── 20_di_san_occurrence_2023_2025.csv   # Mốc tổ chức thực tế các năm 2023–2025
└── files/
    ├── ich-full.owl                       # TBox + ABox gộp (RDF/XML) – MỞ FILE NÀY TRONG PROTÉGÉ
    ├── ich-tbox.ttl                       # Lược đồ lớp (Classes), thuộc tính (Properties) & ràng buộc logic
    ├── ich-abox.ttl                       # Dữ liệu thực thể, cá thể, occurrence & cặp dễ nhầm lẫn
    ├── catalog-v001.xml                   # OASIS XML Catalog định tuyến import TBox cục bộ cho Protégé
    ├── abox_registry.py                   # Module nạp và chuẩn hóa dữ liệu curated từ CSV vào RDF
    ├── gen_ich_owl.py                     # Script sinh tự động ich-tbox.ttl, ich-abox.ttl, ich-full.owl
    ├── verify_ich.py                      # Script kiểm tra OWL 2 DL profile, HermiT consistency & SPARQL
    ├── verify_report.txt                  # Báo cáo kết quả kiểm thử HermiT & entailment
    └── README_Protege.md                  # Hướng dẫn chi tiết sử dụng OntoGraf, DL Query trong Protégé
```

---

