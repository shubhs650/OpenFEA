# Primary reference register

Checked 2026-10-12. Architectural recommendations are original project decisions; sources substantiate tool capabilities and operational constraints, not a claim that this combination has been tested. Exact dependency APIs must be checked again against locked versions during M0.

| ID | Primary source | Use / limitation |
|---|---|---|
| S01 | https://www.dhondt.de/ | Official CalculiX downloads, version 2.23 listing, source and test examples; use pinned build docs |
| S02 | https://www.dhondt.de/ccx_2.22.pdf | Accessible indexed CCX manual reference; not authoritative for a later binary without checking differences |
| S03 | https://dhondt.de/ccx_2.23.pdf | Version-matched manual candidate; direct retrieval failed during planning, must obtain and read before keyword implementation |
| S04 | https://gmsh.info/doc/texinfo/ | Stable Gmsh manual, OCC import, mesh API, sizing fields, high-order options and copying conditions |
| S05 | https://github.com/Open-Cascade-SAS/OCCT/blob/master/dox/user_guides/modeling_algos/modeling_algos.md | Official OCCT modeling algorithms including defeaturing; master is not a version pin |
| S06 | https://kitware.github.io/vtk-js/docs/ | vtk.js scientific web visualization; exact volume/filter support must be validated |
| S07 | https://learn.chatgpt.com/docs/agent-configuration/agents-md | Canonical AGENTS.md discovery; Agent.md alone is not default discovery |
| S08 | https://learn.chatgpt.com/docs/environments/cloud-environments | Current cloud environment setup/publish flow; account UI can differ |
| S09 | https://learn.chatgpt.com/docs/environments/cloud-environment | Legacy setup-script guidance only for accounts still using that flow |
| S10 | https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html | Budget notifications can lag actual charges; alerts are not hard enforcement |
| S11 | https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html | Regional bucket selection; no blanket locality promise for every surrounding service |
| S12 | https://ansyshelp.ansys.com/public/Views/Secured/corp/v242/en/ans_vm/Hlp_V_VMTOC.html | Official verification case index; verify applicability and reproduction rights per case |
| S13 | https://www.code-aster.org/V2/doc/default/en/index.php | Candidate official documentation entry; retrieval failed during planning, exact reference case unresolved |

No AWS hourly prices have been verified or quoted. F8/T033 must collect dated Indian-region prices rather than using numbers from memory. No proprietary verification model or manual is included in this kit.
