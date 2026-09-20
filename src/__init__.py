"""Pipeline package. Deliberately empty at foundation stage.

The pipeline phase adds, in this order (Architecture Freeze v1.1):
normalisation -> entity extraction -> KB retrieval (deterministic first),
then the frozen pretrained encoders. Foundation-stage shared code lives in
src/kb.py and src/foundation_audit.py only.
"""
