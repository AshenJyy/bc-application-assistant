from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .preflight import check_environment


def main(argv: list[str] | None = None) -> int:
    # Host relays send UTF-8 JSON bytes. Windows' locale-dependent pipe decoder
    # can otherwise corrupt smart punctuation, accented names and Chinese text.
    for stream in (sys.stdin,sys.stdout):
        if callable(getattr(stream,'reconfigure',None)):
            stream.reconfigure(encoding='utf-8',errors='strict')
    parser = argparse.ArgumentParser(description="BC Application Assistant local tools")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight", help="Check local prerequisites; never writes website data")
    preflight.add_argument("--psr", type=Path)
    preflight.add_argument("--profile-dir", type=Path, required=True)
    preflight.add_argument("--browser", choices=["chrome", "edge"], required=True)
    for command in ('school-lookup-resolve','school-lookup-remember'):
        lookup=commands.add_parser(command,help='Public school directory evidence; no application input')
        lookup.add_argument('--profile',type=Path,required=True)
        lookup.add_argument('--school',required=True)
    parse = commands.add_parser("parse-psr", help="Extract raw PSR academic records; no website actions")
    parse.add_argument("psr", type=Path)
    parse.add_argument("--output", type=Path, required=True, help="Private extraction path; refuses overwrite")
    init = commands.add_parser("profile-init",help="Create one complete canonical JSON from a required PSR")
    init.add_argument("--psr",type=Path,required=True)
    init.add_argument("--profile",type=Path,required=True)
    update = commands.add_parser("profile-update",help="Apply a factual operation batch atomically")
    update.add_argument("--profile",type=Path,required=True)
    update.add_argument('--append-new-student-facts',action='store_true',help='During a generic journal, append explicitly supplied new student facts; existing data stays frozen')
    operation_input=update.add_mutually_exclusive_group(required=True)
    operation_input.add_argument("--operations",type=Path)
    operation_input.add_argument("--stdin",action="store_true",help="Read operations without a duplicate personal-data file")
    summary = commands.add_parser("profile-summary",help="Show counts and blockers; no personal values")
    summary.add_argument("--profile",type=Path,required=True)
    collection=commands.add_parser('collection-agenda',help='Read-only deduplicated factual gaps across observed target pages')
    collection.add_argument('--profile',type=Path,required=True)
    workflow=commands.add_parser('workflow-preview',help='Read-only joined school/academic source agenda; no website actions')
    workflow.add_argument('--profile',type=Path,required=True)
    generic=commands.add_parser('generic-preview',help='Read-only semantic source gates and deduplicated factual gaps')
    generic.add_argument('--profile',type=Path,required=True)
    preview = commands.add_parser("evidence-preview",help="Render one temporary page next to the private profile; manual review only")
    preview.add_argument("--profile",type=Path,required=True)
    preview.add_argument("--source",required=True)
    preview.add_argument("--page",type=int,required=True)
    preview.add_argument("--output",type=Path,required=True)
    for command in ("page-plan", "page-prepare", "page-verify", "page-restore", "page-verify-matching", "uc-term-preview",
                    "uc-term-prepare","uc-term-verify","uc-term-recover","uc-refill-prepare",
                    "uc-refill-grades","uc-refill-recover","uc-refill-verify","coverage-inventory","common-ielts-resume","common-page-resume",
                    "common-language-preview","common-language-prepare","common-language-rows","common-language-resume","common-language-verify","common-language-cancel",
                    "common-academic-preview","common-academic-prepare","common-academic-advance","common-academic-verify","common-academic-cancel",
                    "common-school-preview","common-school-prepare","common-school-advance","common-school-verify","common-school-recover","common-school-cancel",
                    "common-current-preview","common-current-prepare","common-current-advance","common-current-verify","common-current-recover","common-current-cancel",
                    "generic-resume","generic-recover","generic-cancel","generic-stage","generic-stage-accept","generic-stage-restart","generic-acknowledge-save","generic-view-prepare"):
        page_command = commands.add_parser(command,help="Private host relay; page JSON read from stdin, no browser connection")
        page_command.add_argument("--profile",type=Path,required=True)
        if command in {"page-plan","page-verify-matching","uc-term-preview","uc-term-prepare","uc-refill-prepare","coverage-inventory","common-language-preview","common-language-prepare","common-academic-preview","common-academic-prepare","common-school-preview","common-school-prepare","common-current-preview","common-current-prepare","generic-stage"}:
            page_command.add_argument("--target",required=True)
        else:
            page_command.add_argument("--checkpoint",required=True)
        if command in {'common-academic-preview','common-academic-prepare','common-school-preview','common-school-prepare','common-current-preview','common-current-prepare'}:
            page_command.add_argument('--report-ref',required=True)
        if command in {"page-verify","uc-term-verify","uc-refill-grades","uc-refill-verify","common-school-verify","common-current-verify"}:
            page_command.add_argument("--restoration",action="store_true")
    args = parser.parse_args(argv)
    if args.command == "evidence-preview":
        from .profile import ProfileError
        from .store import ProfileStore
        from .evidence import render_preview
        try:
            snapshot=ProfileStore(args.profile).load()
            result=render_preview(snapshot.data,args.source,page=args.page,output=args.output,profile_path=args.profile)
            print(json.dumps(result,ensure_ascii=False))
            return 0
        except ProfileError as exc:
            print(json.dumps({"ok":False,"error":str(exc)}))
            return 2
        except (OSError,ValueError,TypeError):
            print(json.dumps({"ok":False,"error":"evidence_preview_failed"}))
            return 2
    if args.command.startswith(("page-","uc-term-","uc-refill-","common-language-","common-academic-","common-school-","common-current-","school-lookup-","generic-")) or args.command in {'coverage-inventory','common-ielts-resume','common-page-resume','collection-agenda','workflow-preview'}:
        from .profile import ProfileError
        from .store import ProfileStore
        from . import pages
        try:
            payload = json.load(sys.stdin)
            store = ProfileStore(args.profile)
            snapshot = store.load()
            if args.command.startswith('generic-'):
                from . import generic_forms
                if args.command=='generic-preview':result=generic_forms.preview(snapshot.data,payload['requests'])
                elif args.command=='generic-stage':result=generic_forms.prepare_stage(snapshot.data,args.target,payload['page'],payload['analysis'],payload['context'],payload['controller_key'],reaffirm_native_select=payload.get('reaffirm_native_select') is True)
                elif args.command=='generic-stage-restart':result=generic_forms.restart_stage(snapshot.data,args.checkpoint,payload['page'],payload['analysis'],payload['controller_key'],reaffirm_native_select=payload.get('reaffirm_native_select') is True)
                elif args.command=='generic-stage-accept':result=generic_forms.accept_stage(snapshot.data,args.checkpoint,payload['page'],payload['analysis'])
                elif args.command=='generic-view-prepare':result=generic_forms.switch_view(snapshot.data,args.checkpoint,payload['previous_page'],payload['page'],payload['analysis'],controller_key=payload.get('controller_key'))
                elif args.command=='generic-resume':result=generic_forms.resume(snapshot.data,args.checkpoint,payload['page'],payload.get('analysis'))
                elif args.command=='generic-recover':result=generic_forms.recovery(snapshot.data,args.checkpoint,payload['page'])
                elif args.command=='generic-acknowledge-save':result=generic_forms.acknowledge_save(snapshot.data,args.checkpoint,payload['receipt'])
                else:result=generic_forms.cancel(snapshot.data,args.checkpoint,payload['page'],revisited_saved_draft=payload.get('revisited_saved_draft') is True)
            elif args.command=='workflow-preview':
                from .workflow import agenda
                result=agenda(snapshot.data,payload['steps'],payload['routes'])
            elif args.command=='collection-agenda':
                from .intake import agenda
                result=agenda(snapshot.data,payload['requests'])
            elif args.command.startswith('school-lookup-'):
                from . import schools
                result=(schools.resolve_lookup(snapshot.data,args.school,payload['lookup']) if args.command.endswith('resolve') else
                    schools.remember_lookup(snapshot.data,args.school,payload['lookup'],payload['context']))
            elif args.command.startswith('common-current-'):
                from . import common_current
                operation=args.command.removeprefix('common-current-')
                if operation=='preview':result=common_current.preview(snapshot.data,args.target,args.report_ref,payload['page'])
                elif operation=='prepare':result=common_current.prepare(snapshot.data,args.target,args.report_ref,payload['page'],payload['context'])
                elif operation=='advance':result=common_current.advance(snapshot.data,args.checkpoint,payload['page'])
                elif operation=='recover':result=common_current.recovery(snapshot.data,args.checkpoint,payload['page'])
                elif operation=='verify':result=common_current.verify(snapshot.data,args.checkpoint,payload['page'],revisited_after_save=payload.get('revisited_after_save') is True,restoration=args.restoration)
                else:result=common_current.cancel(snapshot.data,args.checkpoint,payload['page'],revisited_saved_draft=payload.get('revisited_saved_draft') is True)
            elif args.command.startswith('common-school-'):
                from . import common_schools
                operation=args.command.removeprefix('common-school-')
                if operation=='preview':result=common_schools.preview(snapshot.data,args.target,args.report_ref,payload['page'])
                elif operation=='prepare':result=common_schools.prepare(snapshot.data,args.target,args.report_ref,payload['page'],payload['context'])
                elif operation=='advance':result=common_schools.advance(snapshot.data,args.checkpoint,payload['page'])
                elif operation=='recover':result=common_schools.recovery(snapshot.data,args.checkpoint,payload['page'])
                elif operation=='verify':result=common_schools.verify(snapshot.data,args.checkpoint,payload['page'],revisited_after_save=payload.get('revisited_after_save') is True,restoration=args.restoration)
                else:result=common_schools.cancel(snapshot.data,args.checkpoint,payload['page'],revisited_saved_draft=payload.get('revisited_saved_draft') is True)
            elif args.command.startswith('common-academic-'):
                from . import common_academic
                operation=args.command.removeprefix('common-academic-')
                if operation=='preview':result=common_academic.preview(snapshot.data,args.target,args.report_ref,payload['page'])
                elif operation=='prepare':result=common_academic.prepare(snapshot.data,args.target,args.report_ref,payload['page'],payload['context'])
                elif operation=='advance':result=common_academic.advance(snapshot.data,args.checkpoint,payload['page'])
                elif operation=='verify':result=common_academic.verify(snapshot.data,args.checkpoint,payload['page'],revisited_after_save=payload.get('revisited_after_save') is True)
                else:result=common_academic.cancel(snapshot.data,args.checkpoint,payload['page'],revisited_saved_draft=payload.get('revisited_saved_draft') is True)
            elif args.command.startswith('common-language-'):
                from . import common_language
                operation=args.command.removeprefix('common-language-')
                if operation=='preview':result=common_language.preview(snapshot.data,args.target,payload['page'])
                elif operation=='prepare':result=common_language.prepare(snapshot.data,args.target,payload['page'],payload['context'])
                elif operation=='rows':result=common_language.prepare_rows(snapshot.data,args.checkpoint,payload['page'])
                elif operation=='resume':result=common_language.resume(snapshot.data,args.checkpoint,payload['page'])
                elif operation=='verify':result=common_language.verify(snapshot.data,args.checkpoint,payload['page'],revisited_after_save=payload.get('revisited_after_save') is True)
                else:result=common_language.cancel(snapshot.data,args.checkpoint,payload['page'],revisited_saved_draft=payload.get('revisited_saved_draft') is True)
            elif args.command=='coverage-inventory':
                from .coverage import inventory
                result=inventory(snapshot.data,args.target,payload['pages'],payload['routes'])
            elif args.command=='common-ielts-resume':
                from .common_ielts import resume
                result=resume(snapshot.data,args.checkpoint,payload['page'])
            elif args.command=='common-page-resume':
                from .common_pages import resume
                result=resume(snapshot.data,args.checkpoint,payload['page'])
            elif args.command.startswith('uc-refill-'):
                from .uc_course_refill import prepare_refill,prepare_grades,recover_refill,verify_refill
                if args.command=='uc-refill-prepare':result=prepare_refill(snapshot.data,args.target,payload['bundle'],payload['context'],
                    reaffirm_term_keys=payload.get('reaffirm_term_keys'))
                elif args.command=='uc-refill-grades':result=prepare_grades(snapshot.data,args.checkpoint,payload['page'],restoration=args.restoration)
                elif args.command=='uc-refill-recover':result=recover_refill(snapshot.data,args.checkpoint)
                else:result=verify_refill(snapshot.data,args.checkpoint,payload['bundle'],
                    revisited_after_save=payload.get('revisited_after_save') is True,restoration=args.restoration)
            elif args.command=='uc-term-preview':
                from .uc_term_setup import preview_term_availability
                result=preview_term_availability(snapshot.data,args.target,payload['page'])
            elif args.command=='uc-term-prepare':
                from .uc_term_setup import prepare_term_test
                result=prepare_term_test(snapshot.data,args.target,payload['bundle'],payload['context'])
            elif args.command=='uc-term-verify':
                from .uc_term_setup import verify_term_test
                result=verify_term_test(snapshot.data,args.checkpoint,payload['bundle'],
                    revisited_after_save=payload.get('revisited_after_save') is True,restoration=args.restoration)
            elif args.command=='uc-term-recover':
                from .uc_term_setup import recover_term_test,recover_term_warning
                result=(recover_term_warning(snapshot.data,args.checkpoint) if payload.get('post_warning_cancel') is True
                    else recover_term_test(snapshot.data,args.checkpoint,payload['bundle']))
            elif args.command == "page-plan":
                result = pages.build_plan(snapshot.data,args.target,payload["page"],optional_keys=payload.get("optional_keys"),reaffirm_keys=payload.get('reaffirm_keys'),semantic_analysis=payload.get('analysis'))
            elif args.command=='page-verify-matching':
                result=pages.verify_matching(snapshot.data,args.target,payload['baseline'],payload['page'],payload['context'],
                    revisited_saved_draft=payload.get('revisited_saved_draft') is True,semantic_analysis=payload.get('analysis'))
            elif args.command == "page-prepare":
                result = pages.prepare(snapshot.data,args.checkpoint,payload["page"],payload["context"])
            elif args.command == "page-verify":
                result = pages.verify_saved(snapshot.data,args.checkpoint,payload["page"],
                    revisited_after_save=payload.get("revisited_after_save") is True,restoration=args.restoration)
            else:
                result = pages.recovery_bundle(snapshot.data,args.checkpoint,payload["page"])
            if args.command not in {"page-restore","uc-term-preview","uc-term-recover","uc-refill-recover","coverage-inventory","collection-agenda","workflow-preview","generic-preview","generic-recover","common-language-preview","common-academic-preview","common-school-preview","common-school-recover","common-current-preview","common-current-recover","school-lookup-resolve"} and (
                    args.command!='page-verify-matching' or result['verified']) and (
                    args.command not in {'common-language-prepare','common-academic-prepare','common-school-prepare','common-current-prepare','school-lookup-remember'} or result['ready']) and (
                    args.command!='school-lookup-remember' or result['profile_changed']):
                store.save(snapshot)
            print(json.dumps(result,ensure_ascii=False,allow_nan=False))
            return 0
        except ProfileError as exc:
            print(json.dumps({"ok":False,"error":str(exc)}))
        except (OSError,ValueError,TypeError,KeyError):
            print(json.dumps({"ok":False,"error":"page_operation_failed"}))
        return 2
    if args.command.startswith("profile-"):
        from .profile import ProfileError,create_profile,review_requirements,check_sources
        from .store import ProfileStore,ProfileSnapshot
        from .psr import PSRError
        try:
            store = ProfileStore(args.profile)
            if args.command == "profile-init":
                snapshot = ProfileSnapshot(create_profile(args.psr),None)
                store.save(snapshot)
            else:
                snapshot = store.load()
                if args.command == "profile-update":
                    from .operations import apply_operations
                    operations = json.load(sys.stdin) if args.stdin else json.loads(args.operations.read_text(encoding="utf-8"))
                    apply_operations(snapshot.data,operations)
                    store.save(snapshot,explicit_new_fact_ids=[op['field'] for op in operations if op.get('op')=='fact'] if args.append_new_student_facts else ())
            data = snapshot.data
            print(json.dumps({"ok":True,"schema_version":data["schema_version"],"revision":data["revision"],
                "courses":len(data["academic"]["courses"]),"facts":len(data["facts"]),"exams":len(data["exams"]),
                "targets":len(data["targets"]),"unresolved_reviews":len(review_requirements(data)),
                "clarifications_needed":sum(r["student_clarification_required"] for r in review_requirements(data)),
                "source_issues":check_sources(data),"website_actions_performed":False}))
            return 0
        except (ProfileError,PSRError) as exc:
            print(json.dumps({"ok":False,"error":str(exc)}))
        except (OSError,ValueError,TypeError,KeyError) as exc:
            print(json.dumps({"ok":False,"error":"profile_operation_failed"}))
        return 2
    if args.command == "parse-psr":
        from .psr import PSRError, parse_psr
        try:
            result = parse_psr(args.psr)
            with args.output.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
        except (PSRError, OSError) as exc:
            error = str(exc) if isinstance(exc, PSRError) else "output_unwritable_or_already_exists"
            print(json.dumps({"ok": False, "error": error}))
            return 2
        print(json.dumps({"ok": True, "courses": len(result["courses"]), "schools": len(result["schools"]),
                          "review_requirements": len(result["review_requirements"]), "verification": result["verification"]}))
        return 0
    result = check_environment(args.psr, args.profile_dir, args.browser)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["local_checks_passed"] else 2
