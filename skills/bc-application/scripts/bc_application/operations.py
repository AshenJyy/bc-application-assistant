"""Apply explicitly supplied factual edits to one in-memory transaction."""
from . import profile as model


def apply_operations(profile: dict, operations: list[dict]) -> dict[str,str]:
    try:
        return _apply_operations(profile,operations)
    except model.ProfileError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise model.ProfileError("invalid_operation_structure") from exc


def _apply_operations(profile: dict, operations: list[dict]) -> dict[str,str]:
    if not isinstance(operations,list):
        raise model.ProfileError("operation_list_required")
    aliases: dict[str,str] = {}
    for operation in operations:
        if not isinstance(operation,dict) or "op" not in operation:
            raise model.ProfileError("operation_object_required")
        op = operation["op"]
        source_id = aliases.get(operation.get("source"),operation.get("source"))
        if op == "statement":
            alias = operation.get("id")
            if not alias or alias in aliases:
                raise model.ProfileError("unique_statement_alias_required")
            aliases[alias] = model.add_statement(profile,operation["text"],scope=operation.get("scope"),
                                               origin=operation.get("origin","student"))
        elif op == 'exam_release_schedule':
            alias = operation.get('id')
            if not alias or alias in aliases:
                raise model.ProfileError('unique_schedule_alias_required')
            aliases[alias] = model.register_exam_release_schedule(profile, system=operation['system'],
                year=operation['year'], release_date=operation['release_date'], url=operation['url'],
                title=operation['title'], excerpt=operation['excerpt'], observation_method=operation['observation_method'])
        elif op == "fact":
            model.set_fact(profile,operation["field"],operation["value"],source_id,
                           scale=operation.get("scale"),evidence=operation.get("evidence"),kind=operation.get("kind","factual"))
        elif op == "marker_explanation":
            model.clarify_marker(profile,operation["records"],meaning=operation["meaning"],statement_source_id=source_id)
        elif op == "review_clarification":
            model.clarify_review(profile,operation["review_id"],source_id)
        elif op == "document":
            from pathlib import Path
            alias = operation.get("id")
            if not alias or alias in aliases:
                raise model.ProfileError("unique_document_alias_required")
            aliases[alias] = model.register_document(profile,Path(operation["path"]),kind=operation["kind"])
        elif op == "document_review":
            model.review_with_document(profile,operation["review_id"],source_id,page=operation["page"],quote=operation["quote"],
                method=operation.get("method","text_quote"),bbox=operation.get("bbox"))
        elif op == "relink_document":
            from pathlib import Path
            model.relink_document(profile,source_id,Path(operation["path"]))
        elif op == "exam":
            exam_id=model.add_exam(profile,name=operation["name"],system=operation["system"],score=operation["score"],
                scale=operation["scale"],source_id=source_id,related_course_ids=operation.get("related_courses"),evidence=operation.get("evidence"),
                date=operation.get('date'),date_evidence=operation.get('date_evidence'))
            if operation.get('id'):
                if operation['id'] in aliases:raise model.ProfileError('unique_exam_alias_required')
                aliases[operation['id']]=exam_id
        elif op == 'exam_date':
            model.set_exam_date(profile,aliases.get(operation['exam'],operation['exam']),operation['value'],source_id,
                                evidence=operation.get('evidence'))
        elif op == 'exam_date_ref':
            key=aliases.get(operation['exam'],operation['exam']);field=operation['field']
            exam=profile['exams'].get(key);fact=profile['facts'].get(field,{})
            if (not exam or not field.startswith('exams.') or model._source(profile,source_id)['kind']!='student_statement'
                    or exam.get('date_fact_id') not in {None,field} or not fact.get('source_refs')):
                raise model.ProfileError('explicit_existing_exam_date_reference_required')
            model.validate_exam_date(fact.get('value'))
            from .checkpoints import page_requirements
            if not page_requirements(profile,fact_ids=[field])['data_ready']:raise model.ProfileError('exam_date_source_requires_review')
            exam['date_fact_id']=field
            model._event(profile,'existing_exam_date_fact_linked',[key,field,source_id])
        elif op == "schedule":
            model.set_course_schedule(profile,operation["record"],duration=operation["duration"],source_id=source_id,
                term_label=operation.get("term_label"),start_date=operation.get("start_date"),end_date=operation.get("end_date"))
        elif op == 'application_site':
            from .generic_forms import bind_site
            bind_site(profile,aliases.get(operation['target'],operation['target']),operation['url'],source_id)
        elif op == "target":
            alias = operation.get("id")
            if not alias or alias in aliases:
                raise model.ProfileError("unique_target_alias_required")
            aliases[alias] = model.add_target(profile,system=operation["system"],school=operation["school"],
                program=operation.get("program"),source_id=source_id)
        elif op == "bind_fact":
            target_id = aliases.get(operation["target"],operation["target"])
            model.bind_fact(profile,target_id,operation["field_key"],operation["fact"],page_path=operation.get('page_path'))
        elif op == "bind_record_column":
            target_id = aliases.get(operation["target"],operation["target"])
            model.bind_record_column(profile,target_id,operation["field_key"],operation["record"],operation["column"],page_path=operation.get('page_path'))
        elif op == 'scope_bindings':
            target_id=aliases.get(operation['target'],operation['target'])
            model.scope_bindings(profile,target_id,operation['page_path'],operation['field_keys'])
        elif op == "resolve_conflict":
            model.resolve_conflict(profile,operation["conflict_id"],choose=operation["choose"],confirmation_source_id=source_id)
        else:
            raise model.ProfileError("operation_not_supported")
    model.validate_profile(profile)
    return aliases
