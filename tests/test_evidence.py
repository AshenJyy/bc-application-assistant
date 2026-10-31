import copy
import io
from pathlib import Path

import pdfplumber
import pytest
from PIL import Image,ImageDraw,ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from bc_application.cli import main
from bc_application.evidence import render_preview
from bc_application.profile import (ProfileError,add_statement,clarify_marker,create_profile,
    register_document,review_requirements,review_with_document,set_fact,validate_profile)
from bc_application.store import ProfileSnapshot,ProfileStore

FIXTURE=Path(__file__).parent/'fixtures/synthetic_psr.pdf'


@pytest.fixture
def scanned(tmp_path):
    # Real text is rasterized so automatic text extraction cannot be substituted
    # for the explicit manual-review method under test.
    image=Image.new('RGB',(1000,440),'white')
    draw=ImageDraw.Draw(image); font=ImageFont.load_default(size=28)
    lines=['SYNTHETIC REPORT CARD - NOT A VALID STUDENT RECORD',
        'AP CALCULUS BC 12A','Equivalency credit; original school result 93%',
        'No exam score is inferred from this report card.']
    for index,line in enumerate(lines): draw.text((20,30+index*80),line,font=font,fill='black')
    buffer=io.BytesIO(); image.save(buffer,format='PNG'); buffer.seek(0)
    source=tmp_path/'scanned_report_card.pdf'
    pdf=canvas.Canvas(str(source),pagesize=A4,invariant=1)
    pdf.drawImage(ImageReader(buffer),30,430,width=535,height=235)
    pdf.save()
    data=create_profile(FIXTURE)
    document=register_document(data,source,kind='report_card')
    record=next(c for c in data['academic']['courses'] if c['raw_cells']['equivalency_marker'])
    store=ProfileStore(tmp_path/'applicant.json'); snapshot=ProfileSnapshot(data,None); store.save(snapshot)
    return snapshot.data,document,record['record_id'],source,store


def explanation(data,record):
    statement=add_statement(data,'For this invented record only the marker denotes equivalency credit.',scope=[record])
    clarify_marker(data,[record],meaning='equivalency_credit',statement_source_id=statement)
    return review_requirements(data,record)[0]['review_id']


def test_scanned_preview_contains_pixels_but_never_claims_extracted_facts(scanned):
    data,document,_,source,store=scanned
    before_profile=store.path.read_bytes(); before_pdf=source.read_bytes()
    output=store.path.parent/'review.png'
    result=render_preview(data,document,page=1,output=output,profile_path=store.path)
    assert result['manual_review_required'] and not result['text_extraction_performed']
    assert result['coordinate_system']=='pdf_points_top_origin'
    with Image.open(output) as pixels:
        assert pixels.width>1000 and pixels.height>1500
        assert pixels.convert('L').getextrema()==(0,255)
    with pdfplumber.open(source) as pdf: assert not pdf.pages[0].extract_text()
    assert source.read_bytes()==before_pdf and store.path.read_bytes()==before_profile


def test_visual_review_requires_statement_and_stays_separate_from_text_extraction(scanned):
    data,document,record,_,_=scanned
    review=review_requirements(data,record)[0]['review_id']
    with pytest.raises(ProfileError,match='student_clarification'):
        review_with_document(data,review,document,page=1,quote='Equivalency credit',method='visual_review',bbox=[30,170,565,415])
    explanation(data,record)
    with pytest.raises(ProfileError,match='text_layer_missing'):
        review_with_document(data,review,document,page=1,quote='Equivalency credit')
    original=copy.deepcopy(data['academic'])
    review_with_document(data,review,document,page=1,quote='Equivalency credit; original school result 93%',
        method='visual_review',bbox=[30,170,565,415])
    evidence=data['reviews'][review]['document_evidence']
    assert evidence['method']=='visual_review' and evidence['bbox']==[30,170,565,415]
    assert not review_requirements(data,record)
    assert data['academic']==original and data['facts']=={} and data['exams']=={}
    assert data['marker_explanations'][record]['verification']=='student_reported'
    validate_profile(data)


def test_manual_review_cannot_promote_an_oral_value_to_automatic_extraction(scanned):
    data,document,_,_,_=scanned
    before=copy.deepcopy(data)
    with pytest.raises(ProfileError,match='manual_review_does_not_establish_automatic_extraction'):
        set_fact(data,'education.grade',93,document,evidence={'page':1,'quote':'93%',
            'method':'visual_review','bbox':[30,170,565,415]})
    assert data==before


@pytest.mark.parametrize('bbox', [None,[-1,0,10,10],[0,0,0,10],[0,0,9999,9999],[0,0,float('inf'),10]])
def test_invalid_visual_locator_cannot_resolve_a_record(scanned,bbox):
    data,document,record,_,_=scanned
    review=explanation(data,record)
    with pytest.raises(ProfileError,match='visual_review_'):
        review_with_document(data,review,document,page=1,quote='Equivalency credit',method='visual_review',bbox=bbox)
    assert review_requirements(data,record)[0]['transcript_or_report_card_review_required']


@pytest.mark.parametrize('failure',['exists','outside','wrong_extension','missing','changed'])
def test_preview_limits_preserve_existing_files_and_source_recovery(scanned,failure,tmp_path):
    data,document,_,source,store=scanned
    output=tmp_path/'review.png'; expected='preview_'
    if failure=='exists': output.write_bytes(b'Preserve existing artifact')
    if failure=='outside':
        other=tmp_path/'other'; other.mkdir(); output=other/'review.png'
    if failure=='wrong_extension': output=tmp_path/'review.pdf'
    if failure=='missing': source.unlink(); expected='evidence_document_unavailable'
    if failure=='changed': source.write_bytes(b'Changed source'); expected='evidence_document_changed'
    with pytest.raises(ProfileError,match=expected):
        render_preview(data,document,page=1,output=output,profile_path=store.path)
    if failure=='exists': assert output.read_bytes()==b'Preserve existing artifact'
    else: assert not output.exists()
    validate_profile(data)


def test_preview_cli_does_not_mutate_profile_or_report_doc_verification(scanned,capsys):
    _,document,_,_,store=scanned
    before=store.path.read_bytes(); output=store.path.parent/'review.png'
    assert main(['evidence-preview','--profile',str(store.path),'--source',document,'--page','1','--output',str(output)])==0
    printed=capsys.readouterr().out
    assert 'manual_review_required' in printed and '93%' not in printed
    assert store.path.read_bytes()==before
