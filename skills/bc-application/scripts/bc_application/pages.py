"""Whole-page plans, durable rollback journals and saved-state verification."""
from __future__ import annotations
import copy
import re

from .adapters import get_adapter
from .browser import digest, permission_gate, structure, validate_observation, values
from .checkpoints import create_checkpoint, page_requirements, transaction_active
from .profile import ProfileError, _event, now

SAFE_PREFIXES = {"personal", "contact", "address", "family", "education", "exams", "schedules", "activities"}


def resolve(profile: dict, ref: str) -> tuple[object, list[str]]:
    from .source_refs import is_metadata,metadata_value
    if is_metadata(ref):return metadata_value(profile,ref),[]
    if ref.startswith("psr:"):
        # Split at the last colon: PSR record IDs themselves include colons.
        record_id, column = ref[4:].rsplit(":", 1)
        course = next((c for c in profile["academic"]["courses"] if c["record_id"] == record_id), None)
        from .profile import RAW_BINDABLE_COLUMNS
        raw_column = "course_description" if column == "description" else column
        if not course or column not in RAW_BINDABLE_COLUMNS or not course["raw_cells"].get(raw_column):
            raise ProfileError("raw_academic_value_missing_or_unsupported")
        return course["raw_cells"][raw_column], [record_id]
    if ref.split(".")[0] not in SAFE_PREFIXES or ref not in profile["facts"]:
        raise ProfileError("explicit_factual_value_required")
    if ref == "personal.birth_date":
        from .adapters.mit import birth_date
        import calendar
        parsed = birth_date(profile["facts"][ref]["value"])
        permitted = {"personal.birth_month":{str(parsed.month),f"{parsed.month:02}",calendar.month_name[parsed.month].lower()},
            "personal.birth_day":{str(parsed.day),f"{parsed.day:02}"}, "personal.birth_year":{str(parsed.year)}}
        if any(key in profile["facts"] and str(profile["facts"][key]["value"]).lower() not in allowed
               for key,allowed in permitted.items()):
            raise ProfileError("contradictory_birth_date_facts")
    return profile["facts"][ref]["value"], []


def encode(field: dict, value: object) -> object:
    control = field["control"]
    if control in {'material_select','choice_input'}:
        if not isinstance(value,str):raise ProfileError('explicit_material_label_required')
        if value==field['value'] and control=='material_select':return value
        matches=[o for o in field.get('choices',[]) if o['label']==value and not o['disabled']]
        if len(matches)!=1:raise ProfileError('observed_material_choices_required')
        return value
    if control == "checkbox":
        if not isinstance(value, bool):
            raise ProfileError("explicit_boolean_required")
        return value
    if control in {"select", "radio"}:
        options = [o for o in field["options"] if not o.get("disabled")]
        if control=='select' and isinstance(value,dict) and set(value)=={'label','group'} and all(isinstance(v,str) and v for v in value.values()):
            matches=[o for o in options if o['label']==value['label'] and o.get('group')==value['group']]
        elif isinstance(value, bool):
            label = "yes" if value else "no"
            matches = [o for o in options if o["label"].strip().lower() == label]
        elif isinstance(value, (str, int)) and not isinstance(value, bool):
            # Prefer an exact display label; never fuzzy-match a country/grade.
            matches = [o for o in options if o["label"].strip() == str(value)]
            if not matches:
                matches = [o for o in options if o["value"] == str(value)]
        else:
            matches = []
        if len(matches) != 1:
            raise ProfileError("observed_option_exact_match_required")
        return matches[0]["value"]
    if control not in {"text", "textarea", "email", "tel", "number", "date"} or not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise ProfileError("factual_control_value_unsupported")
    return str(value)


def build_plan(profile: dict, target_id: str, page: dict, *, optional_keys: list[str] | None = None,
               reaffirm_keys: list[str] | None = None, semantic_analysis: dict | None = None) -> dict:
    validate_observation(page)
    if page.get('scope',{}).get('kind')=='common_app_grade_creation':
        raise ProfileError('dedicated_academic_creation_workflow_required')
    # Check before requirement updates: conditional fields must never reset an
    # interrupted checkpoint or replace its durable recovery journal.
    if any(transaction_active(cp) for cp in profile["checkpoints"].values()) or (semantic_analysis or {}).get('parent_checkpoint_id'):
        from .generic_forms import active_parent
        active_parent(profile,target_id,page,semantic_analysis)
    target = profile["targets"].get(target_id)
    if not target:
        raise ProfileError("student_selected_target_required")
    try:
        from .generic_forms import adapter_for,plan_details
        adapter = adapter_for(profile,target,page,semantic_analysis)
    except ValueError as exc:
        raise ProfileError(str(exc)) from exc
    reaffirm=set(reaffirm_keys or [])
    optional = set(optional_keys or []) | reaffirm
    if 'generic_form' in page:
        optional.update(i['key'] for i in adapter.items.values() if i['role']=='factual')
    if not reaffirm <= {f['key'] for f in page['fields']}:raise ProfileError('observed_reaffirmation_field_required')
    policy=adapter.collection_policy(profile,page)
    required_facts, courses, blockers, manual, writes, recommendations = list(policy['fact_ids']), [], [], [], [], []
    record_columns = {}
    desired_writes = {}
    blockers.extend(adapter.page_blockers(page))
    blockers.extend(adapter.fact_blockers(profile,page))
    if not policy['allowed']:
        blockers.append({'reason':'repeatable_record_editors_not_supported',
                         'collection_count':len(page['collections'])})
    if page.get("frames_present"):
        blockers.append({"reason":"embedded_form_not_supported"})
    for f in page["fields"]:
        required = adapter.required_for_page(f,page)
        if required and re.search(r'optional\b',f['label']+' '+f.get('group',''),re.I):
            blockers.append({'field_key':f['key'],'label':f['label'],'reason':'conflicting_required_signals'})
            # A contradictory website signal is not a request for invented data.
            continue
        if not required and f["key"] not in optional and adapter.skip_optional_unsupported(f):
            continue
        if adapter.manual(f):
            if f['key'] not in optional and adapter.skip_blank_optional_manual(f,page):
                continue
            # Saving a page containing an essay/declaration could transmit it too.
            manual.append(f["key"])
            continue
        ref = adapter.binding_for_page(f, target, profile, page)
        recommendations.extend(adapter.recommendations(f, ref))
        if f.get("disabled") or f.get("readonly"):
            if required and (f["value"] == "" or f["value"] is None):
                blockers.append({"field_key":f["key"], "reason":"required_control_not_editable"})
            continue
        if not ref:
            if required or f["key"] in optional:
                blockers.append({"field_key":f["key"], "label":f["label"], "reason":"unmapped_required_factual_field"})
            continue
        if not required and f["key"] not in optional:
            continue
        from .source_refs import is_metadata
        if not ref.startswith("psr:") and not is_metadata(ref):
            required_facts.append(ref)
        try:
            supplied, record_ids = resolve(profile, ref)
            courses.extend(record_ids)
            if ref.startswith("psr:"):
                record_id,column = ref[4:].rsplit(":",1)
                record_columns.setdefault(record_id,[]).append(column)
            encoded = encode({**f,'choices':page.get('choice_observations',{}).get(f['key'],[])}, adapter.display_value(f,ref,supplied))
        except (ProfileError, ValueError) as exc:
            blockers.append({"field_key":f["key"], "reason":str(exc)})
            continue
        desired_writes[f['key']]={"field_key":f['key'],"fact_ref":ref,"value":encoded}
        numeric_input=bool('generic_form' in page and ref.startswith('psr-average:') and adapter.items[f['key']].get('format')=='decimal_fixed_2')
        if f['key'] in reaffirm:
            choices=page.get('choice_observations',{}).get(f['key'],[])
            native=f['control'] in {'select','radio'} and bool(encoded) and any(o['value']==encoded and not o.get('disabled') for o in f['options'])
            if not native and (f['control'] not in {'material_select','choice_input'} or not encoded or not any(o['value']==encoded and not o['disabled'] for o in choices)):
                blockers.append({'field_key':f['key'],'reason':'observed_material_reaffirmation_required'})
                continue
        if encoded != f["value"] or f['key'] in reaffirm or numeric_input:
            if 'uc_course_editor' in page and encoded != f['value'] and not re.search(r'_class_title$|_grade[12](?:Other)?$',f['key']):
                blockers.append({'field_key':f['key'],'reason':'uc_course_reconfiguration_requires_workflow'})
                continue
            if page.get('scope') and (re.match(r'i:(schoolName|schoolYear|gradingScale|schedule)Control',f['key']) or
                    (f['control']=='material_select' and not f['value'])):
                blockers.append({'field_key':f['key'],'reason':'existing_course_values_only'})
                continue
            writes.append({"field_key":f["key"], "fact_ref":ref, "value":encoded,**({'numeric_input':True} if numeric_input else {})})
        if f.get("invalid") and encoded == f["value"] and not numeric_input:
            blockers.append({"field_key":f["key"], "reason":"website_validation_unresolved"})
    for key in adapter.dependent_field_keys(page,writes):
        if key not in desired_writes:
            blockers.append({'field_key':key,'reason':'dependent_factual_value_required'})
            continue
        writes=[w for w in writes if w['field_key']!=key]
        writes.append(desired_writes[key])
    gate = page_requirements(profile, fact_ids=list(dict.fromkeys(required_facts)),
        course_ids=list(dict.fromkeys(courses)), manual_fields=manual,record_columns=record_columns)
    action = adapter.save_action(page)
    if not action:
        blockers.append({"reason":"unique_observed_draft_save_required"})
    if not gate["data_ready"]:
        blockers.append({"reason":"page_data_gate_failed", "details":gate})
    checkpoint_id = create_checkpoint(profile, target_id, page["url"], fact_ids=required_facts,
        course_ids=courses, manual_fields=manual,record_columns=record_columns,
        instance_key=adapter.checkpoint_instance() if 'generic_form' in page else None)
    cp = profile["checkpoints"][checkpoint_id]
    cp.pop('verification_kind',None)
    cp.update({"state":"planned" if not blockers else "blocked", "observed_structure":structure(page),
               "observation_sha256":digest(page), "optional_keys":sorted(optional),'reaffirm_keys':sorted(reaffirm), "journal":None,
               "bindings":{f["key"]:adapter.binding_for_page(f,target,profile,page) for f in page["fields"] if not adapter.manual(f)},
               "save_action":action, "source_gate":gate})
    if 'generic_form' in page:cp['semantic_analysis']=copy.deepcopy(adapter.analysis)
    _event(profile,"observed_page_planned",[checkpoint_id])
    return {"schema":"page-plan/1", "checkpoint_id":checkpoint_id, "ready":not blockers,
        "system":target["system"], "allowed_origin":adapter.application_origin,
        "page_url":page["url"], "observation_sha256":digest(page), "structure_sha256":digest(structure(page)),
        "expected_values_sha256":digest({**values(page), **{w["field_key"]:w["value"] for w in writes}}),
        "writes":writes, "save_action":action, "blockers":blockers, "recommendations":recommendations,
        **(plan_details(profile,page,adapter,gate,blockers) if 'generic_form' in page else {}),
        **({'collection_policy':policy} if page.get('collections') else {}),
        **({'editor_state':page['editor_state'],'choice_observations':page.get('choice_observations',{})} if 'editor_state' in page else {}),
        **({'common_ielts':page['common_ielts'],'choice_observations':page['choice_observations']} if 'common_ielts' in page else {}),
        **({'common_factual':page['common_factual'],'choice_observations':page['choice_observations']} if 'common_factual' in page else {}),
        **({'uc_course_editor':page['uc_course_editor'],'uc_course_parent':page['uc_course_parent'],
            'uc_academic_auxiliary':page['uc_academic_auxiliary']} if 'uc_course_editor' in page else {})}


def prepare(profile: dict, checkpoint_id: str, page: dict, context: dict) -> dict:
    cp = profile["checkpoints"].get(checkpoint_id)
    if not cp or cp["state"] != "planned":
        raise ProfileError("ready_observed_plan_required")
    validate_observation(page)
    from .generic_forms import adapter_for,permission
    target=profile['targets'][cp['target_id']]
    adapter = adapter_for(profile,target,page,cp.get('semantic_analysis'))
    permission_gate(context, page, adapter.application_origin)
    if 'generic_form' in page:permission(profile,target,page,context)
    if digest(page) != cp["observation_sha256"]:
        raise ProfileError("page_changed_since_plan")
    # Re-evaluate facts/sources so a plan cannot bypass an intervening conflict.
    plan = build_plan(profile, cp["target_id"], page, optional_keys=cp["optional_keys"],reaffirm_keys=cp.get('reaffirm_keys',[]),semantic_analysis=cp.get('semantic_analysis'))
    if not plan["ready"]:
        raise ProfileError("page_no_longer_ready")
    original = values(page)
    # Keep one temporary page snapshot in the canonical file. Browser validation
    # can normalize other fields, so a delta-only journal cannot restore them.
    journal = dict(original)
    cp.update({"state":"prepared", "journal":journal, "prepared_at":now(),
               "transaction_profile_revision":profile["revision"]+1, "context":dict(context),
               "expected_values_sha256":digest({**original, **{w["field_key"]:w["value"] for w in plan["writes"]}}),
               "original_values_sha256":digest(original)})
    if 'generic_form' in page:
        cp.update(prepared_plan=copy.deepcopy(plan),generic_original_structure_sha256=digest(structure(page)),
            generic_original_invalid_fields=sorted(f['key'] for f in page['fields'] if f['invalid']),
            generic_fact_hashes={r:digest(profile['facts'].get(r)) for r in cp['required_fact_ids']},generic_academic_sha256=profile['academic_sha256'],generic_directory_sha256=digest(profile.get('school_directory')))
    if any(tag in page for tag in ('editor_state','mit_coursework','common_ielts','common_factual')) or page.get('state_metadata',{}).get('coverage')=='uc_visible_review_and_draft':
        cp['prepared_plan']=copy.deepcopy(plan)
    if 'editor_state' in page:
        cp['editor_state']=copy.deepcopy(page['editor_state'])
        cp['choice_observations']=copy.deepcopy(page.get('choice_observations',{}))
    if context.get('real_account_test') or any(tag in page for tag in ('common_ielts','common_factual')):
        cp['original_state_metadata']=copy.deepcopy(page['state_metadata'])
        if any(tag in page for tag in ('common_ielts','common_factual')):cp['original_invalid_fields']=sorted(f['key'] for f in page['fields'] if f['invalid'])
        if 'editor_state' in page:cp['original_editor_state']=copy.deepcopy(page['editor_state'])
        if 'uc_course_parent' in page:cp['original_uc_course_parent']=copy.deepcopy(page['uc_course_parent'])
    _event(profile,"page_rollback_journal_prepared",[checkpoint_id])
    return plan


def verify_saved(profile: dict, checkpoint_id: str, page: dict, *, revisited_after_save: bool, restoration: bool = False) -> dict:
    cp = profile["checkpoints"].get(checkpoint_id)
    if cp and cp.get('generic_stage_controller'):raise ProfileError('branch_discovery_requires_whole_page_prepare')
    if cp and cp.get('kind')=='common_academic_creation':raise ProfileError('dedicated_academic_verification_required')
    if cp and cp.get('kind')=='common_school':raise ProfileError('dedicated_school_verification_required')
    if cp and cp.get('language_transaction'):
        raise ProfileError('staged_language_verification_required')
    if cp and cp.get('verification_kind')=='read_only_saved_match':
        raise ProfileError('read_only_saved_match_requires_dedicated_verification')
    if cp and cp.get('kind') in {'uc_school_terms','uc_course_refill'}:
        raise ProfileError('uc_school_terms_dedicated_verification_required')
    if not cp or cp["state"] not in {"prepared", "saved_unverified", "needs_restore", "verified"}:
        raise ProfileError("prepared_checkpoint_required")
    if restoration and cp.get('journal') is None:
        raise ProfileError('rollback_journal_required')
    validate_observation(page)
    if cp.get('semantic_analysis'):
        from .generic_forms import permission,directory_unchanged,collection_actions,source_fingerprint
        permission(profile,profile['targets'][cp['target_id']],page,cp['context'])
        collection_actions(profile,cp['target_id'],page,cp['semantic_analysis'])
        if restoration:raise ProfileError('generic_saved_restoration_unverified_use_unsaved_cancel')
        source_gate=page_requirements(profile,fact_ids=cp['required_fact_ids'],course_ids=cp['required_course_ids'],record_columns=cp.get('required_record_columns'))
        if (profile['academic_sha256']!=cp['generic_academic_sha256'] or not directory_unchanged(profile,cp) or not source_gate['data_ready']
                or any(digest(profile['facts'].get(ref))!=sha for ref,sha in cp['generic_fact_hashes'].items())):
            raise ProfileError('generic_saved_verification_source_changed')
    desired = cp["original_values_sha256"] if restoration else cp["expected_values_sha256"]
    invalid=sorted(f['key'] for f in page['fields'] if f.get('invalid'))
    common=any(tag in page for tag in ('common_ielts','common_factual'))
    validity_matches=(invalid==cp.get('original_invalid_fields',[]) if restoration and common else not invalid)
    valid = (revisited_after_save is True and page["url"] == cp["page_key"] and
             digest(structure(page)) == digest(cp["observed_structure"]) and digest(values(page)) == desired and
             validity_matches)
    if common:
        from .common_pages import state_matches,keys
        original=cp.get('original_state_metadata',{});current=page.get('state_metadata',{})
        valid=valid and (original==current if restoration else state_matches(original,current,*keys(page)))
    if cp.get('context',{}).get('real_account_test'):
        valid = valid and page.get('state_metadata')==cp.get('original_state_metadata')
        if 'original_editor_state' in cp:valid=valid and page.get('editor_state')==cp['original_editor_state']
        if restoration and 'original_uc_course_parent' in cp:
            valid=valid and page.get('uc_course_parent')==cp['original_uc_course_parent']
    if not valid:
        cp["state"] = "needs_restore"
        _event(profile,"saved_page_verification_failed",[checkpoint_id])
        return {"verified":False, "restored":False, "state":"needs_restore"}
    cp["state"] = "restored" if restoration else "verified"
    if cp.get('semantic_analysis'):cp['verified_source_sha256']=source_fingerprint(profile,cp['semantic_analysis'])
    cp["last_verified_at"] = now()
    if restoration or not (cp.get('context',{}).get('real_account_test') or cp.get('context',{}).get('restore_after_test')):
        cp["journal"] = None
        cp.pop('prepared_plan',None)
        for name in ('generic_original_structure_sha256','generic_original_invalid_fields','generic_fact_hashes','generic_academic_sha256','generic_directory_sha256','generic_pending_fact_ids'):
            cp.pop(name,None)
        cp.pop('choice_observations',None)
        cp.pop('editor_state',None)
        cp.pop('original_invalid_fields',None)
        if 'original_state_metadata' in cp:
            cp['restored_state_sha256']=digest(cp.pop('original_state_metadata'))
        if 'original_editor_state' in cp:cp['restored_editor_sha256']=digest(cp.pop('original_editor_state'))
        if 'original_uc_course_parent' in cp:cp['restored_parent_sha256']=digest(cp.pop('original_uc_course_parent'))
    _event(profile,"page_restored" if restoration else "saved_page_verified",[checkpoint_id])
    return {"verified":True, "restored":restoration, "state":cp["state"]}


def verify_matching(profile: dict, target_id: str, baseline: dict, saved: dict, context: dict, *, revisited_saved_draft: bool, semantic_analysis: dict | None = None) -> dict:
    """Verify a separate saved read without input, saving, or a rollback journal."""
    if 'generic_form' in baseline or 'generic_form' in saved:
        from .generic_forms import verify_matching as generic_match
        return generic_match(profile,target_id,baseline,saved,context,revisited_saved_draft=revisited_saved_draft,analysis=semantic_analysis)
    if any(transaction_active(cp) for cp in profile['checkpoints'].values()):
        raise ProfileError('pending_transaction_requires_recovery')
    target=profile['targets'].get(target_id)
    if not target or target['system']!='common_app' or baseline.get('scope'):
        raise ProfileError('supported_common_native_matching_page_required')
    adapter=get_adapter(target['system'])
    for page in (baseline,saved):
        validate_observation(page);permission_gate(context,page,adapter.application_origin)
    if context.get('real_account_test'):raise ProfileError('read_only_matching_context_required')
    from .browser import validate_common_state
    for page in (baseline,saved):validate_common_state(page.get('state_metadata',{}))
    def complete(page):
        state=page['state_metadata']
        return any(i['key']==state['current_page_key'] and i['status']=='complete' for i in state['items'])
    if (revisited_saved_draft is not True or baseline['url']!=saved['url'] or not complete(baseline) or not complete(saved)
            or digest(structure(baseline))!=digest(structure(saved)) or values(baseline)!=values(saved)
            or baseline['state_metadata']!=saved['state_metadata']
            or baseline.get('choice_observations',{})!=saved.get('choice_observations',{})
            or any(f['invalid'] for page in (baseline,saved) for f in page['fields'])):
        return {'verified':False,'reason':'independent_saved_draft_match_required','website_actions_performed':False}
    working=copy.deepcopy(profile)
    first=build_plan(working,target_id,baseline)
    second=build_plan(working,target_id,saved)
    if not first['ready'] or first['writes'] or not second['ready'] or second['writes']:
        return {'verified':False,'reason':'source_ready_unchanged_matching_plan_required','website_actions_performed':False}
    cp=working['checkpoints'][second['checkpoint_id']]
    cp.update(state='verified',journal=None,context=dict(context),verification_kind='read_only_saved_match',
        expected_values_sha256=digest(values(saved)),saved_state_sha256=digest(saved['state_metadata']),last_verified_at=now())
    for key in ('prepared_plan','original_state_metadata','original_invalid_fields','original_values_sha256',
                'prepared_at','transaction_profile_revision'):
        cp.pop(key,None)
    _event(working,'matching_saved_page_verified_without_input',[second['checkpoint_id']])
    profile.clear();profile.update(working)
    return {'verified':True,'checkpoint_id':second['checkpoint_id'],'state':'verified',
        'verification_kind':'read_only_saved_match','fields':len(saved['fields']),
        'visible_states':len(saved['state_metadata']['items']),'website_actions_performed':False}


def restoration_writes(profile: dict, checkpoint_id: str, page: dict) -> list[dict]:
    cp = profile["checkpoints"].get(checkpoint_id)
    if cp and cp.get('semantic_analysis'):raise ProfileError('generic_unsaved_cancel_or_intended_resume_required')
    if cp and cp.get('kind')=='common_academic_creation':raise ProfileError('academic_unsaved_cancel_or_resume_required')
    if cp and cp.get('kind')=='common_school':raise ProfileError('dedicated_school_recovery_required')
    if cp and cp.get('language_transaction'):
        raise ProfileError('staged_language_cancel_or_resume_required')
    if not cp or cp.get("journal") is None:
        raise ProfileError("rollback_journal_required")
    validate_observation(page)
    if page["url"] != cp["page_key"] or digest(structure(page)) != digest(cp["observed_structure"]):
        raise ProfileError("restoration_structure_changed_handoff_required")
    current = values(page)
    writes=[{"field_key":key,"value":value} for key,value in cp['journal'].items() if current[key]!=value]
    if page.get('common_factual',{}).get('kind')=='language':
        adapter=get_adapter(profile['targets'][cp['target_id']]['system'])
        for key in adapter.dependent_field_keys(page,writes):
            writes=[w for w in writes if w['field_key']!=key]
            writes.append({'field_key':key,'value':cp['journal'][key]})
    return writes


def recovery_bundle(profile: dict, checkpoint_id: str, page: dict) -> dict:
    """Restart recovery using only the one canonical profile and fresh UI."""
    writes = restoration_writes(profile,checkpoint_id,page)
    cp = profile['checkpoints'][checkpoint_id]
    return {'writes':writes, **({'plan':copy.deepcopy(cp['prepared_plan']),
        'context':{**cp['context'],'journal_persisted':True},
        **({'original_state_metadata':copy.deepcopy(cp['original_state_metadata']),
            'original_values_sha256':cp['original_values_sha256']} if cp.get('original_state_metadata',{}).get('coverage') in
                {'mit_visible_review_and_draft','uc_visible_review_and_draft'} or any(tag in cp.get('observed_structure',{}) for tag in ('common_ielts','common_factual')) else {}),
        **({'original_invalid_fields':list(cp['original_invalid_fields'])} if 'original_invalid_fields' in cp else {})}
        if 'prepared_plan' in cp else {})}


def execute(profile_snapshot, store, checkpoint_id: str, port, context: dict, *, restore_test: bool = False) -> dict:
    """Reference port orchestration; production uses documented host-tool relay.

    Persist the one-file rollback journal before any write, verify only after a
    save and revisit, and restore even if writing/readback fails during a test.
    """
    profile = profile_snapshot.data
    if context.get("real_account_test") and not restore_test:
        raise ProfileError("real_account_test_requires_restoration")
    if restore_test:context={**context,'restore_after_test':True}
    plan = prepare(profile,checkpoint_id,port.observe(),context)
    store.save(profile_snapshot)
    profile = profile_snapshot.data
    result = None
    try:
        port.write(plan["writes"])
        after_fill = port.observe()
        # Conditional new fields/choices reopen collection BEFORE a draft save.
        if digest(structure(after_fill)) != plan["structure_sha256"]:
            raise ProfileError("conditional_page_changed_collect_before_save")
        if any(f.get("invalid") for f in after_fill["fields"]):
            raise ProfileError("website_validation_unresolved")
        if digest(values(after_fill)) != plan["expected_values_sha256"]:
            raise ProfileError("unexpected_page_values_before_save")
        port.save_draft(plan["save_action"])
        profile["checkpoints"][checkpoint_id]["state"] = "saved_unverified"
        store.save(profile_snapshot)
        profile = profile_snapshot.data
        port.revisit(plan["page_url"])
        result = verify_saved(profile,checkpoint_id,port.observe(),revisited_after_save=True)
        store.save(profile_snapshot)
        profile = profile_snapshot.data
    except Exception:
        profile["checkpoints"][checkpoint_id]["state"] = "needs_restore"
        store.save(profile_snapshot)
        profile = profile_snapshot.data
        if not restore_test:
            raise
    finally:
        if restore_test:
            port.revisit(plan["page_url"])
            writes = restoration_writes(profile,checkpoint_id,port.observe())
            port.write(writes)
            port.save_draft(plan["save_action"])
            port.revisit(plan["page_url"])
            restored = verify_saved(profile,checkpoint_id,port.observe(),revisited_after_save=True,restoration=True)
            store.save(profile_snapshot)
            if not restored["restored"]:
                raise ProfileError("restoration_failed_manual_handoff_required")
    return {"fill_verified":bool(result and result["verified"]), "restored":restore_test,
            "state":profile["checkpoints"][checkpoint_id]["state"]}
