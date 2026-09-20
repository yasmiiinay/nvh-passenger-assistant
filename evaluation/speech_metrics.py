"""Speech metrics (RQ2). Definitions per Evidence Pack section A4.

WER is computed at two normalisation levels and BOTH are always reported:
  L1: generic normalisation only (raw ASR quality; the headline number)
  L2: L1 plus the airport-specific normaliser
L1 - L2 is the measured benefit of the domain normaliser. Number words are
normalised at BOTH levels (following the Whisper paper's own normaliser);
only airport-specific repairs (letter words, spacing, terminal forms) are L2.

Both levels use src/normalizer.py so that the WER transform and the pipeline's
own text handling cannot drift apart: what the retrieval stage sees is
exactly the L2 string scored here. jiwer supplies the alignment only.
"""
from __future__ import annotations

from src.normalizer import normalize_l1, normalize_l2


def _wer(references: list[str], hypotheses: list[str], normaliser) -> dict:
    import jiwer  # imported here so the harness file parses without the env
    if len(references) != len(hypotheses):
        raise ValueError("references and hypotheses must have the same length")
    refs = [normaliser(r) for r in references]
    hyps = [normaliser(h) for h in hypotheses]
    empty = [i for i, r in enumerate(refs) if not r]
    if empty:
        raise ValueError(f"empty reference after normalisation at index {empty[0]}")
    words_only = jiwer.Compose([jiwer.ReduceToListOfListOfWords()])
    out = jiwer.process_words(refs, hyps, reference_transform=words_only,
                              hypothesis_transform=words_only)
    return {"wer": out.wer, "substitutions": out.substitutions,
            "deletions": out.deletions, "insertions": out.insertions,
            "hits": out.hits, "n_utterances": len(references)}


def wer_l1(references: list[str], hypotheses: list[str]) -> dict:
    """WER (standard normalisation): lowercase, contractions, punctuation,
    whitespace, cardinal number words -> digits, applied to both sides."""
    return _wer(references, hypotheses, normalize_l1)


def wer_l2(references: list[str], hypotheses: list[str]) -> dict:
    """WER (domain normalisation): L1 plus the airport rules on both sides."""
    return _wer(references, hypotheses, normalize_l2)


def identifier_token_accuracy(reference_identifiers: list[list[str]],
                              hypothesis_texts: list[str], gazetteers,
                              level: str = "L2") -> dict:
    """Share of utterances (among those with >=1 reference identifier) whose
    EVERY reference identifier appears, in canonical form, among the
    identifiers extracted from the processed hypothesis.

    `level` selects the text the extractor sees: "L2" is the pipeline path;
    "L1" runs the extractor on generically-normalised text only, so that the
    L1/L2 pair isolates what the airport rules repair. The returned
    `errors` list is the substitution catalogue for the report
    (reference identifiers vs what was actually extracted).
    """
    from src.entities import extract
    if level not in ("L1", "L2"):
        raise ValueError("level must be 'L1' or 'L2'")
    if len(reference_identifiers) != len(hypothesis_texts):
        raise ValueError("reference_identifiers and hypothesis_texts must have the same length")
    n = correct = 0
    errors: list[dict] = []
    for refs, hyp in zip(reference_identifiers, hypothesis_texts):
        if not refs:
            continue
        n += 1
        found = {e.value for e in extract(hyp, gazetteers, domain_rules=(level == "L2")).entities
                 if e.type in ("gate_id", "desk_id", "belt_id")}
        missing = [r for r in refs if r not in found]
        if missing:
            errors.append({"reference": list(refs), "extracted": sorted(found), "hypothesis": hyp})
        else:
            correct += 1
    return {"accuracy": (correct / n) if n else None, "n": n, "level": level, "errors": errors}


def propagation_gap(retrieval_acc_from_reference: float,
                    retrieval_acc_from_asr: float, n: int) -> dict:
    """Audio-to-retrieval propagation gap (same query set on both sides)."""
    return {"gap": retrieval_acc_from_reference - retrieval_acc_from_asr,
            "retrieval_acc_reference": retrieval_acc_from_reference,
            "retrieval_acc_asr": retrieval_acc_from_asr, "n": n}


def write_artifacts(*args, **kwargs):
    raise NotImplementedError("TODO(speech evaluation phase): persist to outputs/evaluation/speech/")
