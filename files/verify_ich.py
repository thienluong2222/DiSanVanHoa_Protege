#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_ich.py - Kiểm ich-tbox.ttl + ich-test-abox.ttl.

  1. OWL 2 DL profile: OWLAPI (bundled trong HermiT.jar của owlready2) + kiểm Python
     (non-simple property không cardinality/functional/asymmetric/...; regularity của chain).
  2. HermiT: (a) owlready2 sync_reasoner_hermit (suy ra property assertion), (b) HermiT CLI trên
     RDF/XML nguyên bản (đối chứng, không qua bộ nối tiếp của owlready2).
  3. 4 truy vấn SPARQL trên ABox test (không cần reasoner, dùng property path).
  4. Test âm: các vi phạm cố ý phải bị HermiT báo inconsistent.

Chạy:  python3 verify_ich.py [thư_mục_chứa_ttl]       (cần: rdflib, owlready2, Java)
"""
import io
import math
import subprocess
import sys
import tempfile
import warnings
from collections import defaultdict
from contextlib import redirect_stdout
from pathlib import Path

from rdflib import Graph, URIRef, BNode, Literal, RDF, RDFS, OWL, XSD
from rdflib.collection import Collection

warnings.filterwarnings("ignore")

ICH = "https://example.org/ich#"
EXN = "https://example.org/ich/data#"
TBOX_IRI = "https://example.org/ich"
ABOX_IRI = "https://example.org/ich/test-abox"
PFX = f"""PREFIX ich: <{ICH}> PREFIX ex: <{EXN}>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> """
CUE_PATH = ("(ich:hasCue|ich:hasDistinctiveCue|ich:typicallyIncludes|ich:involvesRole|ich:hasTemporalCue"
            "|(ich:typicallyIncludes/ich:usedObjectOfType))")

HERE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp(prefix="ich_verify_"))


def hr(title):
    print("\n" + "=" * 8 + " " + title)


# --------------------------------------------------------------------------
# Nạp & chuyển dạng
# --------------------------------------------------------------------------
def load():
    tb = Graph().parse(HERE / "ich-tbox.ttl", format="turtle")
    ab = Graph().parse(HERE / "ich-test-abox.ttl", format="turtle")
    merged = Graph()
    for t in tb:
        merged.add(t)
    for s, p, o in ab:           # bỏ header + owl:imports của ABox: gộp phẳng cho OWLAPI/HermiT CLI
        if p == OWL.imports or (p == RDF.type and o == OWL.Ontology):
            continue
        merged.add((s, p, o))
    return tb, ab, merged


def hermit_jar():
    import owlready2
    return Path(owlready2.__file__).parent / "hermit" / "HermiT.jar"


def write_rdfxml(g, name):
    path = TMP / name
    g.serialize(path, format="xml")
    return path


def run(cmd, timeout=240):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


# --------------------------------------------------------------------------
# 1. OWL 2 DL profile
# --------------------------------------------------------------------------
DLCHECK_JAVA = """
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.model.*;
import org.semanticweb.owlapi.profiles.*;
import java.io.File;
public class DLCheck {
  public static void main(String[] a) throws Exception {
    OWLOntologyManager m = OWLManager.createOWLOntologyManager();
    OWLOntology o = m.loadOntologyFromOntologyDocument(new File(a[0]));
    System.out.println("axioms=" + o.getAxiomCount() + " logical=" + o.getLogicalAxiomCount());
    OWLProfileReport r = new OWL2DLProfile().checkOntology(o);
    System.out.println("OWL2_DL in_profile=" + r.isInProfile() + " violations=" + r.getViolations().size());
    int i = 0;
    for (OWLProfileViolation v : r.getViolations()) { System.out.println("  - " + v); if (++i >= 20) break; }
  }
}
"""


def check_owlapi_profile(merged_xml):
    src = TMP / "DLCheck.java"
    src.write_text(DLCHECK_JAVA)
    rc, out = run(["java", "-cp", str(hermit_jar()), str(src), str(merged_xml)])
    print(out.strip()[:1500])
    return "in_profile=true" in out


def python_dl_checks(g):
    """Simple-property restrictions + regularity của property chain (OWL 2 Structural Spec, mục 11.1 và 11.2)."""
    ops = set(g.subjects(RDF.type, OWL.ObjectProperty))
    sups, inv = defaultdict(set), {}
    for p, q in g.subject_objects(RDFS.subPropertyOf):
        if p in ops and q in ops:
            sups[p].add(q)
    for p, q in g.subject_objects(OWL.inverseOf):
        inv[p], inv[q] = q, p
    transitive = set(g.subjects(RDF.type, OWL.TransitiveProperty))
    chains = []
    for sup, head in g.subject_objects(OWL.propertyChainAxiom):
        chains.append((list(Collection(g, head)), sup))
    composite = set(transitive) | {sup for parts, sup in chains if len(parts) >= 2}
    changed = True
    while changed:                       # composite lan lên super-property và sang nghịch đảo
        changed = False
        for p in list(composite):
            for q in list(sups.get(p, ())) + ([inv[p]] if p in inv else []):
                if q not in composite:
                    composite.add(q)
                    changed = True
    # property có sub-property composite cũng non-simple (tính theo chiều ngược của sups)
    changed = True
    while changed:
        changed = False
        for p, qs in list(sups.items()):
            if p in composite:
                for q in qs:
                    if q not in composite:
                        composite.add(q)
                        changed = True
    short = lambda x: str(x).replace(ICH, "ich:")
    print("non-simple properties:", ", ".join(sorted(short(p) for p in composite)))
    problems = []
    forbidden = [OWL.FunctionalProperty, OWL.InverseFunctionalProperty, OWL.IrreflexiveProperty, OWL.AsymmetricProperty]
    for p in composite:
        for ft in forbidden:
            if (p, RDF.type, ft) in g:
                problems.append(f"{short(p)} non-simple nhưng khai {str(ft).split('#')[-1]}")
        if p in inv and any((inv[p], RDF.type, ft) in g for ft in forbidden):
            problems.append(f"nghịch đảo của {short(p)} non-simple nhưng khai characteristic bị cấm")
    card_preds = [OWL.cardinality, OWL.minCardinality, OWL.maxCardinality,
                  OWL.qualifiedCardinality, OWL.minQualifiedCardinality, OWL.maxQualifiedCardinality]
    for r in g.subjects(RDF.type, OWL.Restriction):
        p = g.value(r, OWL.onProperty)
        has_card = any((r, cp, None) in g for cp in card_preds) or (r, OWL.hasSelf, None) in g
        if has_card and p in composite:
            problems.append(f"restriction cardinality/hasSelf trên non-simple {short(p)}")
    for a, b in g.subject_objects(OWL.propertyDisjointWith):
        if a in composite or b in composite:
            problems.append(f"propertyDisjointWith với non-simple {short(a)}/{short(b)}")

    # regularity: đồ thị cạnh Ri -> S (gộp property với nghịch đảo) phải không có chu trình
    canon = lambda p: min(p, inv[p], key=str) if p in inv else p
    edges = defaultdict(set)
    for parts, sup in chains:
        for i, ri in enumerate(parts):
            if canon(ri) == canon(sup):
                if i not in (0, len(parts) - 1):
                    problems.append(f"chain cho {short(sup)} chứa chính nó ở giữa")
                continue
            edges[canon(ri)].add(canon(sup))
    color, cyc = {}, []

    def dfs(u, path):
        color[u] = 1
        for v in edges.get(u, ()):
            if color.get(v) == 1:
                cyc.append(path + [v])
            elif v not in color:
                dfs(v, path + [v])
        color[u] = 2
    for n in list(edges):
        if n not in color:
            dfs(n, [n])
    print(f"chains: {len(chains)} | regular order (đồ thị Ri→S không chu trình): {'OK' if not cyc else 'VI PHẠM'}")
    for parts, sup in chains:
        print("   ", " ∘ ".join(short(x) for x in parts), "⊑", short(sup))
    for c in cyc:
        problems.append("chu trình trong thứ tự chain: " + " → ".join(short(x) for x in c))
    # kiểu giá trị: object property không nhận literal, data property không nhận resource
    dps = set(g.subjects(RDF.type, OWL.DatatypeProperty))
    for s, p, o in g:
        if p in ops and isinstance(o, Literal):
            problems.append(f"object property {short(p)} nhận literal ({s})")
        if p in dps and not isinstance(o, Literal):
            problems.append(f"data property {short(p)} nhận resource ({s})")
    print("vi phạm:", problems if problems else "không có")
    return not problems


# --------------------------------------------------------------------------
# 2. HermiT
# --------------------------------------------------------------------------
def hermit_cli(owl_path):
    rc, out = run(["java", "-cp", str(hermit_jar()), "org.semanticweb.HermiT.cli.CommandLine", "-c", str(owl_path)])
    bad = ("Exception" in out) or ("Inconsistent" in out) or rc != 0
    unsat = [l for l in out.splitlines() if "owl:Nothing" in l or "Nothing>" in l and "EquivalentClasses" in l]
    return (not bad), out, unsat


def run_owlready2(tb, ab):
    from owlready2 import World, sync_reasoner_hermit, OwlReadyInconsistentOntologyError
    tb.serialize(TMP / "tbox.nt", format="nt")
    ab.serialize(TMP / "abox.nt", format="nt")
    w = World()
    w.get_ontology(TBOX_IRI).load(fileobj=open(TMP / "tbox.nt", "rb"), format="ntriples")
    w.get_ontology(ABOX_IRI).load(fileobj=open(TMP / "abox.nt", "rb"), format="ntriples")
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            sync_reasoner_hermit(w, infer_property_values=True, debug=0)
        consistent = True
    except OwlReadyInconsistentOntologyError:
        consistent = False
    unsat = [c.name for c in w.inconsistent_classes()] if consistent else []
    return w, consistent, unsat, buf.getvalue()


ENTAIL_JAVA = """
import org.semanticweb.HermiT.Reasoner;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.model.*;
import org.semanticweb.owlapi.reasoner.*;
import java.io.File;
import java.util.*;
public class Entail {
  public static void main(String[] a) throws Exception {
    OWLOntologyManager m = OWLManager.createOWLOntologyManager();
    OWLOntology o = m.loadOntologyFromOntologyDocument(new File(a[0]));
    OWLDataFactory f = m.getOWLDataFactory();
    OWLReasoner r = new Reasoner(o);
    System.out.println("consistent=" + r.isConsistent());
    for (int i = 1; i + 1 < a.length; i += 2) {
      OWLNamedIndividual ind = f.getOWLNamedIndividual(IRI.create(a[i]));
      OWLObjectProperty p = f.getOWLObjectProperty(IRI.create(a[i + 1]));
      Set<String> vals = new TreeSet<String>();
      for (OWLNamedIndividual v : r.getObjectPropertyValues(ind, p).getFlattened()) vals.add(v.getIRI().getFragment());
      System.out.println("VAL " + ind.getIRI().getFragment() + " " + p.getIRI().getFragment() + " = " + String.join(",", vals));
    }
  }
}
"""


def entail(owl_path, pairs):
    """HermiT (OWLAPI) trả về giá trị entailed của object property: {(ind, prop): set(values)}."""
    src = TMP / "Entail.java"
    src.write_text(ENTAIL_JAVA)
    args = []
    for ind, prop in pairs:
        args += [ind if ind.startswith("http") else EXN + ind, ICH + prop]
    rc, out = run(["java", "-cp", str(hermit_jar()), str(src), str(owl_path)] + args)
    res = {}
    for line in out.splitlines():
        if line.startswith("VAL "):
            _, ind, prop, _, vals = (line.split(" ", 4) + [""])[:5]
            res[(ind, prop)] = set(v for v in vals.split(",") if v)
    return res, ("consistent=true" in out)


def entailment_checks(merged_xml, tb):
    ok_all = True
    expect = [  # (individual, property, tập mong đợi ⊆ entailed)
        ("OocOmBocSocTrang", "includesPractice", {"MuaRomVong_Heritage"}),
        ("CholChnamThmay", "includesPractice", {"MuaRomVong_Heritage"}),
        ("MuaRomVong_Heritage", "featuredInEvent", {"OocOmBocSocTrang", "CholChnamThmay"}),
        ("MuaRomVong_Heritage", "featuredIn", {"OocOmBocSocTrang", "CholChnamThmay", "OocOmBocSocTrang_2024"}),
        ("OocOmBocSocTrang", "hasCue", {"GheNgo", "ComDep", "TrangPhucKhmer", "LeCungTrang", "MuaRomVong", "ConDam"}),
        ("ChoNoiCaiRang", "hasCue", {"CayBeo", "MatSongDongGhe", "SangSom", "ThuongHo", "DungCayBeo"}),
        ("ChoNoiPhongDien", "confusableWith", {"ChoNoiCaiRang"}),
        ("SongMaspero_CauQuay_CauCao", "locatedWithin", {"Place_SocTrangArea", "Place_CanThoNewArea"}),
    ]
    res, cons = entail(merged_xml, [(i, p) for i, p, _ in expect])
    print("  [TBox+ABox] HermiT entailment (OWLAPI):")
    for ind, prop, exp in expect:
        got = res.get((ind, prop), set())
        good = exp <= got
        ok_all &= good
        print(f"    {ind}.{prop} ⊇ {sorted(exp)}  {'✓' if good else '✗ thực tế ' + str(sorted(got))}")
    # chain cô lập trên ABox tối thiểu (mỗi lần chỉ một chain có thể kích hoạt)
    pre = f"@prefix ich: <{ICH}> . @prefix ex: <{EXN}> . "
    iso = [
        ("chain 1 typicallyIncludes ∘ realizesPractice ⊑ includesPractice",
         "ex:ev a ich:EventHeritage ; ich:typicallyIncludes ex:act . ex:act a ich:Performance ; ich:realizesPractice ex:pr . ex:pr a ich:PracticeHeritage .",
         [("ev", "includesPractice", {"pr"}), ("pr", "featuredInEvent", {"ev"})]),
        ("chain 2 typicallyIncludes ∘ usedObjectOfType ⊑ hasCue (usedObjectOfType KHÔNG ⊑ hasCue)",
         "ex:ev a ich:EventHeritage ; ich:typicallyIncludes ex:act . ex:act a ich:SocialPractice ; ich:usedObjectOfType ex:obj . ex:obj a ich:VehicleVessel .",
         [("ev", "hasCue", {"act", "obj"})]),
        ("chain 3 featuredInOccurrence ∘ occurrenceOf ⊑ featuredInEvent",
         "ex:pr a ich:PracticeHeritage ; ich:featuredInOccurrence ex:oc . ex:oc a ich:Occurrence ; ich:occurrenceOf ex:ev . ex:ev a ich:EventHeritage .",
         [("pr", "featuredInEvent", {"ev"}), ("pr", "featuredIn", {"ev", "oc"})]),
    ]
    print("  [ABox tối thiểu] mỗi chain chạy riêng:")
    for name, body, exps in iso:
        g = Graph()
        for t in tb:
            g.add(t)
        g.parse(data=pre + body, format="turtle")
        path = write_rdfxml(g, "iso.owl")
        r2, c2 = entail(path, [(i, p) for i, p, _ in exps])
        good = c2 and all(e <= r2.get((i, p), set()) for i, p, e in exps)
        ok_all &= good
        print(f"    {name}: {'✓' if good else '✗ ' + str(r2)}")
    return ok_all


# --------------------------------------------------------------------------
# 3. SPARQL
# --------------------------------------------------------------------------
def q(g, text):
    return list(g.query(PFX + text))


def lab(g, node):
    for o in g.objects(node, RDFS.label):
        if getattr(o, "language", None) == "vi":
            return str(o)
    return str(node).split("#")[-1]


def sparql_suite(g):
    results = {}
    # (a) truy vấn nhiều tầng: cue Rom vong đã link -> tầng 1 (PracticeHeritage) -> tầng 2 (event ứng viên), chấm theo cue còn lại
    hr("(a) Nhiều tầng: Rom vong → ứng viên bối cảnh (cue còn lại trong ảnh: ghe Ngo, thả đèn nước)")
    rows = q(g, f"""
      SELECT ?practice ?event (COUNT(DISTINCT ?c) AS ?support) WHERE {{
        VALUES ?act {{ ich:MuaRomVong }}
        ?act ich:realizesPractice ?practice .
        ?event ich:typicallyIncludes ?act .
        OPTIONAL {{ VALUES ?c {{ ich:GheNgo ich:ThaDenNuoc }} ?event {CUE_PATH} ?c . }}
      }} GROUP BY ?practice ?event ORDER BY DESC(?support)""")
    for r in rows:
        print(f"  tầng 1 = {lab(g, r.practice):<12} | tầng 2 = {lab(g, r.event):<24} | support = {int(r.support)}")
    results["a"] = bool(rows) and lab(g, rows[0].event).startswith("Oóc Om Bóc") and int(rows[0].support) == 2 \
        and all(int(r.support) < 2 for r in rows[1:])

    # (b) cue -> các CueBearer kèm đếm (idf)
    hr("(b) Cue → CueBearer (đếm để tính idf = ln(N/n))")
    N = int(next(iter(q(g, "SELECT (COUNT(DISTINCT ?x) AS ?n) WHERE { ?x rdf:type/rdfs:subClassOf* ich:CueBearer }"))).n)
    rows = q(g, f"""
      SELECT ?cue ?kind (COUNT(DISTINCT ?x) AS ?n) (GROUP_CONCAT(DISTINCT ?xn; separator=", ") AS ?bearers) WHERE {{
        ?x rdf:type/rdfs:subClassOf* ich:CueBearer .
        ?x {CUE_PATH} ?cue .
        OPTIONAL {{ ?cue ich:cueKind ?kind }}
        BIND(REPLACE(STR(?x), "^.*#", "") AS ?xn)
      }} GROUP BY ?cue ?kind ORDER BY DESC(?n) ?cue""")
    print(f"  N (số CueBearer) = {N}")
    print(f"  {'cue':<22}{'kind':<10}{'n':>3}{'idf':>7}  bearers")
    byname = {}
    for r in rows:
        n = int(r.n)
        byname[str(r.cue).split('#')[-1]] = n
        print(f"  {str(r.cue).split('#')[-1]:<22}{str(r.kind):<10}{n:>3}{math.log(N / n):>7.2f}  {r.bearers}")
    results["b"] = (byname.get("CayBeo") == 4 and byname.get("GheNgo") == 1
                    and byname.get("TrangPhucKhmer") == 2 and byname.get("ComDep") == 1)

    # (c) chỉ trả HeritageElement, không trả LookalikeElement
    hr("(c) Lọc đáp án: cue {cây bẹo, ghe thương hồ, sông Cần Thơ} → chỉ HeritageElement")
    cues = "ich:CayBeo ich:GheThuongHo ex:SongCanTho"
    base = f"""
      SELECT ?x (COUNT(DISTINCT ?c) AS ?support) WHERE {{
        VALUES ?c {{ {cues} }}
        ?x rdf:type/rdfs:subClassOf* ich:CueBearer .
        ?x {CUE_PATH} ?c .
        %s
      }} GROUP BY ?x ORDER BY DESC(?support) ?x"""
    allr = q(g, base % "")
    ans = q(g, base % "?x rdf:type/rdfs:subClassOf* ich:HeritageElement . FILTER NOT EXISTS { ?x rdf:type/rdfs:subClassOf* ich:LookalikeElement }")
    print("  Không lọc (mọi CueBearer):  ", ", ".join(f"{lab(g, r.x)}={int(r.support)}" for r in allr))
    print("  Đáp án (chỉ HeritageElement):", ", ".join(f"{lab(g, r.x)}={int(r.support)}" for r in ans))
    print("  → top-1 không lọc hòa điểm giữa Cái Răng và decoy Phong Điền ⇒ pipeline phải hỏi lại 'ở đâu' (discriminator place).")
    ans_names = {str(r.x).split('#')[-1] for r in ans}
    results["c"] = ans_names == {"ChoNoiCaiRang"} and len(allr) == 4

    # (d) EventHeritage có rule trùng một ngày âm (CQ13), xử lý vắt tháng và đúng hệ lịch
    hr("(d) CQ13: EventHeritage có TemporalRule chứa ngày (cùng calendarSystem, vắt tháng)")
    probes = [("vn_lunar", 10, 15, {"OocOmBocSocTrang"}), ("vn_lunar", 8, 30, {"SeneDolta"}),
              ("vn_lunar", 9, 1, {"SeneDolta"}), ("solar", 4, 14, {"CholChnamThmay"}),
              ("khmer_lunar", 10, 15, set()), ("vn_lunar", 4, 14, set())]
    ok = True
    for cal, m, d, expect in probes:
        rows = q(g, f"""
          SELECT DISTINCT ?e WHERE {{
            ?e rdf:type/rdfs:subClassOf* ich:EventHeritage ; ich:hasTemporalRule ?r .
            ?r ich:calendarSystem ?cal ; ich:monthStart ?ms ; ich:monthEnd ?me ; ich:dayStart ?ds ; ich:dayEnd ?de .
            FILTER(?cal = "{cal}")
            BIND(?ms*100+?ds AS ?s) BIND(?me*100+?de AS ?en) BIND({m}*100+{d} AS ?k)
            FILTER( (?s <= ?en && ?k >= ?s && ?k <= ?en) || (?s > ?en && (?k >= ?s || ?k <= ?en)) )
          }}""")
        got = {str(r.e).split('#')[-1] for r in rows}
        ok &= (got == expect)
        shown = str(sorted(got)) if got else "∅"
        print(f"  {cal:<12} {d:>2}/{m:<2} → {shown:<28} {'✓' if got == expect else '✗ mong đợi ' + str(sorted(expect))}")
    results["d"] = ok
    return results


# --------------------------------------------------------------------------
# 4. Test âm
# --------------------------------------------------------------------------
NEG = {
    "N1 một individual vừa HeritageElement vừa LookalikeElement": """
        ex:x a ich:PracticeHeritage , ich:LookalikeElement .""",
    "N2 PracticeHeritage có hasTemporalRule (≤0 + domain EventHeritage)": """
        ex:p a ich:PracticeHeritage ; ich:hasTemporalRule ex:r . ex:r a ich:TemporalRule .""",
    "N3 Occurrence có 2 startDate (=1)": """
        ex:e a ich:EventHeritage . ex:o a ich:Occurrence ; ich:occurrenceOf ex:e ;
          ich:startDate "2024-11-14T00:00:00"^^xsd:dateTime , "2024-11-15T00:00:00"^^xsd:dateTime .""",
    "N4 LookalikeElement dùng typicallyIncludes (domain HeritageElement)": """
        ex:l a ich:LookalikeElement ; ich:typicallyIncludes ex:a . ex:a a ich:Ritual .""",
    "N5 PracticeHeritage typicallyIncludes activity có realizesPractice (chain → includesPractice ∈ EventHeritage)": """
        ex:pr a ich:PracticeHeritage ; ich:typicallyIncludes ex:a .
        ex:a a ich:Performance ; ich:realizesPractice ex:q . ex:q a ich:PracticeHeritage .""",
    "N6 calendarSystem ngoài enum": """
        ex:r a ich:TemporalRule ; ich:calendarSystem "lunar_khmer" .""",
    "N7 monthStart = 13 (ngoài 1..12)": """
        ex:r a ich:TemporalRule ; ich:calendarSystem "solar" ; ich:monthStart 13 .""",
}


def negative_tests(tb):
    prefixes = f"@prefix ich: <{ICH}> . @prefix ex: <{EXN}> . @prefix xsd: <{XSD}> . @prefix owl: <{OWL}> . "
    allok = True
    for name, body in NEG.items():
        g = Graph()
        for t in tb:
            g.add(t)
        g.parse(data=prefixes + body, format="turtle")
        path = write_rdfxml(g, "neg.owl")
        consistent, out, _ = hermit_cli(path)
        verdict = "inconsistent ✓" if not consistent and "Inconsistent" in out else \
            ("lỗi khác ✗: " + out.strip().splitlines()[0][:90] if not consistent else "consistent ✗ (đáng lẽ inconsistent)")
        allok &= (not consistent and "Inconsistent" in out)
        print(f"  {name}\n      → {verdict}")
    return allok


# --------------------------------------------------------------------------
def main():
    tb, ab, merged = load()
    print(f"TBox {len(tb)} triples | ABox {len(ab)} triples | thư mục: {HERE}")
    status = {}

    hr("1. OWL 2 DL profile")
    xml = write_rdfxml(merged, "merged.owl")
    print("[OWLAPI OWL2DLProfile trên TBox+ABox gộp]")
    status["profile_owlapi"] = check_owlapi_profile(xml)
    print("[Kiểm Python: simple property, regularity, kiểu giá trị]")
    status["profile_python"] = python_dl_checks(merged)

    hr("2a. HermiT qua owlready2 (sync_reasoner_hermit, infer_property_values=True)")
    try:
        w, consistent, unsat, log = run_owlready2(tb, ab)
        print("kết quả:", "CONSISTENT" if consistent else "INCONSISTENT", "| class unsatisfiable:", unsat or "không")
        status["owlready2"] = consistent and not unsat
    except Exception as e:                                   # noqa: BLE001
        print("owlready2 lỗi:", type(e).__name__, str(e)[:300])
        status["owlready2"] = False

    hr("2b. HermiT CLI trên RDF/XML nguyên bản (đối chứng)")
    ok, out, unsat = hermit_cli(xml)
    print("kết quả:", "CONSISTENT (classify không lỗi)" if ok else "LỖI/INCONSISTENT: " + out.strip()[:300],
          "| unsatisfiable:", unsat or "không")
    status["hermit_cli"] = ok and not unsat

    hr("2c. Entailment bằng HermiT/OWLAPI (property chain, sub-property, inverse, symmetric, transitive)")
    status["entailments"] = entailment_checks(xml, tb)

    hr("3. SPARQL")
    res = sparql_suite(merged)
    status.update({f"sparql_{k}": v for k, v in res.items()})

    hr("4. Test âm (phải inconsistent)")
    status["negative"] = negative_tests(tb)

    hr("TỔNG KẾT")
    for k, v in status.items():
        print(f"  {k:<18} {'PASS' if v else 'FAIL'}")
    sys.exit(0 if all(status.values()) else 1)


if __name__ == "__main__":
    main()
