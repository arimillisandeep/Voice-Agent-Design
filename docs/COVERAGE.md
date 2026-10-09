# INSTRUCTION COVERAGE REPORT

> Generated from `docs/traceability.yaml` by `tools/make_coverage_report.py`.
> **Do not edit by hand** - every reference below is mechanically verified by
> `tools/verify_coverage.py` and `tests/test_traceability.py`. Rename a prompt
> heading or delete a test and the build fails.

**64/64** original sections mapped  |  **331** references verified  |  **143** test functions  |  **20/20** mandated scenarios covered

| Status | Count | Meaning |
|---|---|---|
| `both` | 35 | stated in the prompt **and** enforced deterministically in code |
| `code` | 1 | enforced in code only (no model discretion) |
| `prompt` | 9 | model behaviour only (style, tone, phrasing) |
| `tests` | 12 | original worked example, now a replayable scenario + assertions |
| `strengthened` | 6 | v2 adds handling the original lacked |
| `gap` | 1 | **not implemented - needs a business decision** |

---

## Section-by-section

| # | Original instruction | Status | Where it lives |
|---|---|---|---|
| 1 | SYSTEM ROLE (11 responsibilities) | prompt + code | prompt 1. IDENTITY; prompt 3. THE THREE GOLDEN RULES; `homecredit_lap.rules.evaluate`; test test_01_normal_eligible_customer_qualifies |
| 2 | AVAILABLE VARIABLES | prompt | prompt 2. INJECTED CONTEXT; config sample_context.yaml:customer_name; config sample_context.yaml:agent_gender; config sample_context.yaml:language_to_speak |
| 3 | LANGUAGE RULE | strengthened | prompt 11. LANGUAGE; test test_every_declared_language_has_an_overlay_or_is_english; test test_overlays_define_the_required_sections; test test_language_aliases_resolve_to_declared_codes ... |
| 4 | AGENT GENDER RULE | strengthened | prompt 12. AGENT GENDER; test test_gender_marking_values_are_valid; test test_overlays_define_the_required_sections; config languages.yaml:languages |
| 5 | CURRENT DATE AND TIME | prompt | prompt 2. INJECTED CONTEXT; config sample_context.yaml:current_date; config sample_context.yaml:current_time |
| 6 | CONVERSATION STYLE | prompt | prompt 13. VOICE AND STYLE |
| 7 | CUSTOMER-FIRST CONVERSATION RULE | prompt + code | prompt 4. PER-TURN PROCEDURE (follow silently, every turn); prompt 6. PHASES AND THE 7-ITEM CHECKLIST; `homecredit_lap.runtime.process_turn` |
| 8 | INTERNAL STATE | prompt + code | prompt 3. THE THREE GOLDEN RULES; `homecredit_lap.state.CallState`; test test_state_schema_covers_every_dataclass_field; test test_state_schema_records_are_well_formed ... |
| 9 | REQUIRED 7-ITEM CHECKLIST | prompt + code | prompt 6. PHASES AND THE 7-ITEM CHECKLIST; `homecredit_lap.state.CHECKLIST_ITEMS`; `homecredit_lap.state.CHECKLIST_ORDER`; test test_checklist_has_seven_items ... |
| 10 | CRITICAL INFORMATION EXTRACTION RULE | prompt + code | prompt 4. PER-TURN PROCEDURE (follow silently, every turn); `homecredit_lap.runtime.process_turn`; `homecredit_lap.parsing.extract_facts` |
| 11 | OUT-OF-ORDER INFORMATION | prompt + code | prompt 6. PHASES AND THE 7-ITEM CHECKLIST; `homecredit_lap.parsing.extract_facts`; `homecredit_lap.state.CallState.missing_items`; test test_12_out_of_order_bundle ... |
| 12 | MULTIPLE ANSWERS IN ONE RESPONSE | prompt + code | prompt 6. PHASES AND THE 7-ITEM CHECKLIST; `homecredit_lap.parsing.extract_facts`; test test_13_multiple_answers_captured_at_once; test test_extract_multiple_answers |
| 13 | CUSTOMER CORRECTIONS | prompt + code | prompt 6. PHASES AND THE 7-ITEM CHECKLIST; `homecredit_lap.state.CallState.record`; test test_15_correction_replaces_previous_answer; test test_20b_correction_is_audited |
| 14 | AMBIGUOUS INFORMATION | prompt + code | prompt 6. PHASES AND THE 7-ITEM CHECKLIST; `homecredit_lap.rules._needs_clarification`; `homecredit_lap.runtime.CLARIFY_BY_ITEM`; test test_04b_ambiguous_documents_are_clarified_not_assumed ... |
| 15 | CONTRADICTORY INFORMATION | prompt + code | prompt 6. PHASES AND THE 7-ITEM CHECKLIST; `homecredit_lap.state.CallState.record`; test test_15_correction_replaces_previous_answer; test test_16_ambiguous_answers_trigger_clarification |
| 16 | STAGE A: GREETING | prompt | prompt 6. PHASES AND THE 7-ITEM CHECKLIST; prompt 7. VERIFICATION |
| 17 | WRONG CUSTOMER | prompt + code | prompt 7. VERIFICATION; prompt 15. CLOSING LINES; `homecredit_lap.rules.evaluate`; `homecredit_lap.parsing.detect_intents` ... |
| 18 | BUSY CUSTOMER FLOW | prompt + code | prompt 8. NON-QUALIFICATION TERMINALS; `homecredit_lap.tools.LapAgentTools.schedule_callback`; `homecredit_lap.parsing.parse_callback_time`; test test_11_busy_stops_qualification ... |
| 19 | OFFER PRESENTATION | prompt | prompt 6. PHASES AND THE 7-ITEM CHECKLIST; prompt 14. COMPLIANCE (non-negotiable); test test_prompt_requires_preliminary_language |
| 20 | INTEREST AND PRODUCT QUESTIONS | prompt + code | prompt 10. ANSWERING QUESTIONS; prompt 14. COMPLIANCE (non-negotiable); `homecredit_lap.parsing.detect_intents`; test test_17_interest_rate_is_deflected_not_invented ... |
| 21 | EXISTING LOAN / EMI REDUCTION DETECTION | prompt + code | prompt 5. ROUTING PRIORITY; prompt 8. NON-QUALIFICATION TERMINALS; `homecredit_lap.parsing.INTENT_PATTERNS`; `homecredit_lap.rules.evaluate` ... |
| 22 | TRANSFER RESPONSE | prompt + code | prompt 8. NON-QUALIFICATION TERMINALS; prompt 15. CLOSING LINES; `homecredit_lap.tools.LapAgentTools.transfer_lead`; `homecredit_lap.rules.SAY` ... |
| 23 | PROPERTY TYPE | prompt + code | prompt 6. PHASES AND THE 7-ITEM CHECKLIST; prompt APPENDIX A; `homecredit_lap.parsing.parse_property_type`; `homecredit_lap.rules.ELIGIBLE_PROPERTY_TYPES` ... |
| 24 | AGRICULTURAL PROPERTY DISQUALIFICATION | prompt + code | prompt 15. CLOSING LINES; prompt APPENDIX A; `homecredit_lap.rules._disqualifier`; test test_02_agricultural_property_disqualifies ... |
| 25 | OWNERSHIP STATUS | prompt + code | prompt APPENDIX A; `homecredit_lap.parsing.parse_ownership`; test test_08_joint_ownership_is_eligible; test test_08b_ownership_never_disqualifies ... |
| 26 | ORIGINAL DOCUMENTS | prompt + code | prompt 15. CLOSING LINES; prompt APPENDIX A; `homecredit_lap.rules._disqualifier`; `homecredit_lap.parsing.parse_documents` ... |
| 27 | LOAN AMOUNT (75 lakh cap) | prompt + code | prompt 9. THE ₹75 LAKH CAP; prompt APPENDIX B; `homecredit_lap.state.MAX_LOAN_AMOUNT`; `homecredit_lap.rules.ACTION_OFFER_CAP` ... |
| 28 | OCCUPATION | prompt + code | prompt APPENDIX A; `homecredit_lap.parsing.parse_occupation`; `homecredit_lap.rules.ELIGIBLE_OCCUPATIONS`; test test_03d_self_employed_is_never_a_disqualifier ... |
| 29 | INCOME MODE | prompt + code | prompt APPENDIX A; prompt 15. CLOSING LINES; `homecredit_lap.rules._disqualifier`; `homecredit_lap.parsing.parse_income_mode` ... |
| 30 | OCCUPATION + INCOME DECISION TABLE | prompt + code | prompt APPENDIX A; `homecredit_lap.rules._disqualifier`; test test_03b_decision_table_cash_disqualifies_both_occupations; test test_03c_decision_table_bank_continues_for_both_occupations |
| 31 | MARKET VALUE (no threshold) | prompt + code | prompt APPENDIX A; prompt 14. COMPLIANCE (non-negotiable); `homecredit_lap.rules._disqualifier`; test test_26_market_value_has_no_threshold ... |
| 32 | TENURE (3-15 years) | prompt + code | prompt APPENDIX A; prompt 15. CLOSING LINES; prompt APPENDIX B; `homecredit_lap.state.MIN_TENURE_YEARS` ... |
| 33 | COMPLETE ELIGIBILITY TABLE | prompt + code | prompt APPENDIX A; test test_eligible_property_types_match_yaml; test test_eligible_occupations_match_yaml; config product_rules.yaml:eligibility |
| 34 | IMMEDIATE DISQUALIFICATION RULE | prompt + code | prompt 3. THE THREE GOLDEN RULES; prompt 5. ROUTING PRIORITY; `homecredit_lap.rules._disqualifier`; `homecredit_lap.rules.evaluate` ... |
| 35 | DO NOT INVENT ELIGIBILITY CRITERIA | strengthened | prompt 14. COMPLIANCE (non-negotiable); test test_prompt_forbids_invented_criteria; test test_26_market_value_has_no_threshold; config product_rules.yaml:compliance |
| 36 | INTERRUPTIONS | prompt + code | prompt 4. PER-TURN PROCEDURE (follow silently, every turn); prompt 6. PHASES AND THE 7-ITEM CHECKLIST; `homecredit_lap.state.CallState.missing_items`; test test_14_interruption_answers_then_resumes ... |
| 37 | CUSTOMER QUESTIONS DURING QUALIFICATION | prompt | prompt 10. ANSWERING QUESTIONS; test test_17_interest_rate_is_deflected_not_invented |
| 38 | UNRELATED QUESTIONS | prompt | prompt 10. ANSWERING QUESTIONS; test test_19_unrelated_question_does_not_end_call; test test_19b_unrelated_question_does_not_invent_facts |
| 39 | RAG RULES | prompt | prompt 2. INJECTED CONTEXT; prompt 10. ANSWERING QUESTIONS |
| 40 | HANDLING NATURAL SPEECH | prompt + code | prompt 6. PHASES AND THE 7-ITEM CHECKLIST; prompt APPENDIX B; `homecredit_lap.parsing.parse_amount`; `homecredit_lap.parsing.extract_facts` ... |
| 41 | NUMBER INTERPRETATION (Indian conventions) | prompt + code | prompt APPENDIX B; `homecredit_lap.parsing.parse_amount`; `homecredit_lap.parsing._expand_grouped`; test test_parse_amount_indian_conventions ... |
| 42 | CALLBACK TIME | strengthened | prompt 8. NON-QUALIFICATION TERMINALS; `homecredit_lap.parsing.parse_callback_time`; `homecredit_lap.runtime.process_turn`; test test_11c_busy_never_invents_a_time ... |
| 43 | CUSTOMER DECLINES | strengthened | prompt 8. NON-QUALIFICATION TERMINALS; prompt 15. CLOSING LINES; `homecredit_lap.tools.LapAgentTools.mark_do_not_call`; `homecredit_lap.rules.evaluate` ... |
| 44 | CUSTOMER BECOMES UPSET | prompt | prompt 8. NON-QUALIFICATION TERMINALS; prompt 15. CLOSING LINES |
| 45 | CUSTOMER REQUESTS A HUMAN | strengthened | prompt 8. NON-QUALIFICATION TERMINALS |
| 46 | FINAL HANDOFF GATE (11 conditions) | code | `homecredit_lap.rules.gate_report`; `homecredit_lap.state.CallState.all_items_answered`; test test_31_gate_report_blocks_when_any_criterion_fails; test test_28_submit_refuses_while_items_are_missing ... |
| 47 | FINAL QUALIFICATION RESPONSE | prompt + code | prompt 15. CLOSING LINES; `homecredit_lap.rules.SAY`; `homecredit_lap.tools.LapAgentTools.submit_eligibility_facts`; test test_01_normal_eligible_customer_qualifies ... |
| 48 | NO PREMATURE APPROVAL | prompt + code | prompt 14. COMPLIANCE (non-negotiable); `homecredit_lap.rules.SAY`; test test_01b_no_premature_approval_language; test test_prompt_forbids_approval_language |
| 49 | FINAL CALL TERMINATION STATES (5) | prompt + code | prompt 5. ROUTING PRIORITY; prompt 15. CLOSING LINES; `homecredit_lap.state.Terminal`; test test_terminals_in_yaml_cover_the_engine ... |
| 50 | TERMINAL STATE PRIORITY | prompt + code | prompt 5. ROUTING PRIORITY; `homecredit_lap.rules.evaluate`; test test_22_routing_priority_dnc_over_transfer; test test_23_routing_priority_transfer_over_busy ... |
| 51 | FIRST-MISSING-QUESTION RULE | prompt + code | prompt 6. PHASES AND THE 7-ITEM CHECKLIST; `homecredit_lap.state.CallState.first_missing`; `homecredit_lap.rules.ASK`; test test_12b_never_reasks_a_captured_item ... |
| 52 | EXAMPLE: FULL OUT-OF-ORDER RESPONSE | scenario + tests | test test_12_out_of_order_bundle; test test_extract_out_of_order_bundle; scenario out_of_order.yaml |
| 53 | EXAMPLE: MULTIPLE ANSWERS WITH DISQUALIFICATION | scenario + tests | test test_24_routing_priority_disqualification_over_collection; test test_extract_cash_income_bundle; scenario cash_income_bundled.yaml |
| 54 | EXAMPLE: AGRICULTURAL PROPERTY PROVIDED LATE | scenario + tests | test test_25_agricultural_bundled_with_passing_facts_still_disqualifies |
| 55 | EXAMPLE: EXISTING LOAN PROVIDED OUT OF ORDER | scenario + tests | test test_09b_transfer_beats_partially_eligible_facts; scenario existing_loan_transfer.yaml |
| 56 | EXAMPLE: 90 LAKH REQUEST | scenario + tests | test test_07_above_cap_offers_75_lakh_instead_of_rejecting; test test_07b_accepting_cap_rewrites_amount_and_continues; scenario cap_negotiation.yaml |
| 57 | EXAMPLE: TENURE DISQUALIFICATION | scenario + tests | test test_05_06_tenure_out_of_window_disqualifies; scenario tenure_below_minimum.yaml |
| 58 | EXAMPLE: BUSY CUSTOMER | scenario + tests | test test_11_busy_stops_qualification; test test_11b_busy_then_time_booked; scenario busy_callback.yaml |
| 59 | EXAMPLE: CUSTOMER ASKS INTEREST RATE | scenario + tests | test test_17_interest_rate_is_deflected_not_invented |
| 60 | EXAMPLE: CUSTOMER INTERRUPTS | scenario + tests | test test_14_interruption_answers_then_resumes |
| 61 | EXAMPLE: CUSTOMER CHANGES ANSWER | scenario + tests | test test_20_corrected_answer_can_disqualify; scenario correction_disqualifies.yaml |
| 62 | EXAMPLE: QUALIFIED CUSTOMER | scenario + tests | test test_01_normal_eligible_customer_qualifies; scenario qualified.yaml |
| 63 | TESTING BEHAVIOR (20 mandated scenarios) | scenario + tests | test test_01_normal_eligible_customer_qualifies; test test_02_agricultural_property_disqualifies; test test_03_cash_income_disqualifies |
| 64 | BUSINESS RULES MUST NEVER BE OVERRIDDEN  [TRUNCATED IN SOURCE] | **GAP** | prompt 3. THE THREE GOLDEN RULES; prompt 14. COMPLIANCE (non-negotiable); prompt APPENDIX A; config product_rules.yaml:compliance |

---

## Notes, caveats and deliberate changes

**Section 3 - LANGUAGE RULE**

> Original covered English + Hindi only. v2 ships 8 locales with per-language overlays.

**Section 4 - AGENT GENDER RULE**

> Original said 'use forms appropriate to the configured gender' without saying how. Each overlay now carries a conjugation table for strong-gender languages and an explicit gender-neutral instruction for weak/none languages.

**Section 9 - REQUIRED 7-ITEM CHECKLIST**

> Item 5 (occupation + income mode) is two facts; v2 states explicitly when it counts as answered.

**Section 28 - OCCUPATION**

> Original did not cover 'freelancer' classification definitively; v2 treats it as self-employed (confirm).

**Section 31 - MARKET VALUE (no threshold)**

> Preserved exactly: no minimum property value, no LTV cap. test_26 locks this so nobody can silently add one. See CHANGELOG open question 3 — a ₹50 lakh request against a ₹10 lakh property currently qualifies, which is correct per the original but may be commercially unintended.

**Section 35 - DO NOT INVENT ELIGIBILITY CRITERIA**

> The full forbidden list (minimum property value, minimum income, credit score, age limit, LTV, location restriction, collateral...) was compressed out of an early v2 draft and restored after test_prompt_forbids_invented_criteria failed.

**Section 39 - RAG RULES**

> Priority order (system rules > RAG > conversation) preserved; product_context may be empty.

**Section 42 - CALLBACK TIME**

> Original said 'clarify if ambiguous' but never defined ambiguous. v2 returns None for 'later'/'anytime'.

**Section 43 - CUSTOMER DECLINES**

> Original said 'respect the request' with no mechanism. v2 adds a DNC tool + terminal + CRM status.

**Section 45 - CUSTOMER REQUESTS A HUMAN**

> Also added: 'are you a robot?' disclosure handling, which the original lacked entirely. Warm transfer is NOT implemented — see CHANGELOG open question 6.

**Section 49 - FINAL CALL TERMINATION STATES (5)**

> Original listed 5 terminals. v2 has 8: adds do_not_call, wrong_person, abandoned.

**Section 50 - TERMINAL STATE PRIORITY**

> The original stated priority in five places (10, 34, 50, 51, 64) and they disagreed. v2 has one table, one ordered function, and tests for the conflicting cases.

**Section 63 - TESTING BEHAVIOR (20 mandated scenarios)**

> All 20 mandated scenarios are covered. Scenarios 5+6 share one parametrised test and 9+10 share one parametrised test, so 20 scenarios map to 18 test functions; the `mandated_20` block below lists every one explicitly and verify_coverage.py asserts all 20 are accounted for.

**Section 64 - BUSINESS RULES MUST NEVER BE OVERRIDDEN  [TRUNCATED IN SOURCE]**

> The supplied prompt ends mid-sentence at 'Income -> Cash'. Sections after 64 are missing. Property / documents / income / tenure rules were reconstructed from sections 24, 26, 29 and 32 and are fully implemented, but ANY instruction that lived only in the truncated tail is NOT covered. Re-send the tail to close this.

---

## Gaps requiring your input

### Section 64 - BUSINESS RULES MUST NEVER BE OVERRIDDEN  [TRUNCATED IN SOURCE]

The supplied prompt ends mid-sentence at 'Income -> Cash'. Sections after 64 are missing. Property / documents / income / tenure rules were reconstructed from sections 24, 26, 29 and 32 and are fully implemented, but ANY instruction that lived only in the truncated tail is NOT covered. Re-send the tail to close this.

---

## v2 additions with no counterpart in the original

| Addition | Why |
|---|---|
| Compliance: OTP / PIN / Aadhaar / card number guard | Outbound lending call in India; the original had no data-protection instruction. |
| AI-disclosure handling ('are you a robot?') | Original covered only 'can I speak to a person'. |
| Re-ask limit (MAX_REASKS = 2) | Nothing in the original stopped an infinite loop with an uncooperative customer. |
| Do-not-call suppression reaching the CRM | Original said 'respect the request' with no recording mechanism. |
| Customer owns no property (property_type = none) | Original assumed the customer always owns a property. |
| No income source (occupation = none) | Original covered salaried/self-employed only; unemployed/student/retired fell through. |
| Mixed income clarification | Original forced a binary bank/cash answer; 'some cash, some bank' had to be guessed. |
| Config / code / prompt drift detection | The original hardcoded ₹75,00,000 in nine places. |

---

## Section 63 - the 20 mandated test scenarios

| # | Scenario | Tests |
|---|---|---|
| 1 | Normal eligible customer | 3 - `test_01_normal_eligible_customer_qualifies`, `test_01b_no_premature_approval_language`, `test_01c_all_seven_facts_reach_the_lead_payload` |
| 2 | Agricultural property | 3 - `test_02_agricultural_property_disqualifies`, `test_02b_agricultural_stops_the_checklist`, `test_02c_agricultural_detected_from_raw_text` |
| 3 | Cash income | 2 - `test_03_cash_income_disqualifies`, `test_03b_decision_table_cash_disqualifies_both_occupations` |
| 4 | Missing original documents | 1 - `test_04_missing_originals_disqualifies` |
| 5 | Tenure below 3 years | 1 - `test_05_06_tenure_out_of_window_disqualifies` |
| 6 | Tenure above 15 years | 2 - `test_05_06_tenure_out_of_window_disqualifies`, `test_05b_tenure_boundaries_inclusive_are_eligible` |
| 7 | Loan request above 75 lakh | 3 - `test_07_above_cap_offers_75_lakh_instead_of_rejecting`, `test_07b_accepting_cap_rewrites_amount_and_continues`, `test_07c_refusing_cap_disqualifies` |
| 8 | Joint ownership | 3 - `test_08_joint_ownership_is_eligible`, `test_08b_ownership_never_disqualifies`, `test_08c_family_property_is_clarified_not_assumed` |
| 9 | Existing property loan | 3 - `test_09_10_existing_loan_or_emi_routes_to_transfer`, `test_09b_transfer_beats_partially_eligible_facts`, `test_09c_transfer_does_not_ask_remaining_items` |
| 10 | EMI reduction request | 2 - `test_09_10_existing_loan_or_emi_routes_to_transfer`, `test_existing_loan_and_emi_detected_together` |
| 11 | Busy customer | 4 - `test_11_busy_stops_qualification`, `test_11b_busy_then_time_booked`, `test_11c_busy_never_invents_a_time` ... |
| 12 | Out-of-order answers | 3 - `test_12_out_of_order_bundle`, `test_12b_never_reasks_a_captured_item`, `test_12c_checklist_is_never_restarted` |
| 13 | Multiple answers in one response | 2 - `test_13_multiple_answers_captured_at_once`, `test_extract_multiple_answers` |
| 14 | Customer interruption | 2 - `test_14_interruption_answers_then_resumes`, `test_14b_interruption_facts_are_still_captured` |
| 15 | Customer correction | 2 - `test_15_correction_replaces_previous_answer`, `test_20b_correction_is_audited` |
| 16 | Ambiguous documents | 3 - `test_16_ambiguous_answers_trigger_clarification`, `test_04b_ambiguous_documents_are_clarified_not_assumed`, `test_04c_clarified_yes_proceeds` |
| 17 | Customer asks interest rate | 2 - `test_17_interest_rate_is_deflected_not_invented`, `test_17b_rate_question_intent_detected` |
| 18 | Customer refuses the offer | 4 - `test_18_decline_ends_without_pressure`, `test_18b_decline_is_not_misread_as_wrong_person`, `test_18c_dnc_request_is_recorded` ... |
| 19 | Customer asks unrelated questions | 2 - `test_19_unrelated_question_does_not_end_call`, `test_19b_unrelated_question_does_not_invent_facts` |
| 20 | Customer changes an answer | 2 - `test_20_corrected_answer_can_disqualify`, `test_20c_tenure_correction_can_also_disqualify` |

Scenarios 5+6 share one parametrised test and 9+10 share one, so 20 mandated
scenarios map to 18 top-level test functions (47 distinct functions in total).

---

*Regenerate: `PYTHONPATH=src:tools python3 tools/make_coverage_report.py`*
