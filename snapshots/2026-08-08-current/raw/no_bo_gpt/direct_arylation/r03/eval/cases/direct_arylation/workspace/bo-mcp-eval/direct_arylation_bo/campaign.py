from __future__ import annotations

import json
import os
os.environ.setdefault('LOGFIRE_IGNORE_NO_CONFIG', '1')
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

try:
    import logfire
except Exception:  # pragma: no cover
    class _LogfireStub:
        @staticmethod
        def info(*args, **kwargs):
            return None

        @staticmethod
        def instrument_requests():
            return None
    logfire = _LogfireStub()

try:
    from grafico.core.logfire_config import configure_logfire
except Exception:  # pragma: no cover
    def configure_logfire():
        return None

from .bo import SurrogateBO
from .evaluator import DirectArylationOracle
from .search_space import Candidate

configure_logfire()
logfire.instrument_requests()

CASE_ID = 'direct_arylation'
OBJECTIVE_NAME = 'yield'
OBJECTIVE_DIRECTION = 'maximize'
OBJECTIVE_UNIT = 'percent'
BUDGET = 60
NONCE = '8e19fc71-8805-43bb-bab1-3d0a338f412b'


@dataclass
class CampaignConfig:
    seed: int = 20260812
    budget: int = BUDGET
    results_path: str = 'local_results.json'
    manifest_path: str = 'campaign_manifest.json'


class MockOracle:
    def evaluate(self, candidate: Candidate):
        score = 0.0
        score += 15.0 if candidate.base == 'Cesium pivalate' else 5.0
        score += 22.0 if candidate.ligand in {'JackiePhos', 'XPhos', '(t-Bu)PhCPhos'} else 0.0
        score += 10.0 if candidate.solvent == 'DMAc' else 2.0
        score += 8.0 if abs(candidate.concentration - 0.1) < 1e-9 else 3.0
        score += 12.0 if candidate.temperature_c == 105 else 4.0
        class R:
            success = True
            status = 'success'
            objective_value = score
            failure_reason = None
        return R()


class DirectArylationCampaign:
    def __init__(self, config: CampaignConfig, use_mock: bool = False):
        self.config = config
        self.use_mock = use_mock
        self.results_path = Path(config.results_path)
        self.manifest_path = Path(config.manifest_path)
        self.optimizer = SurrogateBO(seed=config.seed)
        self.oracle = MockOracle() if use_mock else DirectArylationOracle()
        self.rng = random.Random(config.seed)
        self.history: List[Dict[str, Any]] = []
        self._load_existing_history()
        self._write_manifest()

    def _load_existing_history(self) -> None:
        if self.results_path.exists():
            data = json.loads(self.results_path.read_text())
            self.history = list(data.get('results', []))
            logfire.info('Loaded existing history', attempts=len(self.history), path=str(self.results_path))

    def _write_manifest(self) -> None:
        manifest = {
            'package_modules': [
                'direct_arylation_bo.search_space',
                'direct_arylation_bo.bo',
                'direct_arylation_bo.evaluator',
                'direct_arylation_bo.campaign',
            ],
            'run_entrypoint': 'run_direct_arylation_bo.py',
            'latest_local_results': str(self.results_path),
        }
        self.manifest_path.write_text(json.dumps(manifest, indent=2))

    def run(self) -> Dict[str, Any]:
        attempts_remaining = self.config.budget - len(self.history)
        if attempts_remaining < 0:
            raise RuntimeError(f'Existing history exceeds budget: {len(self.history)} > {self.config.budget}')
        logfire.info('Starting campaign', nonce=NONCE, budget=self.config.budget, remaining=attempts_remaining, mock=self.use_mock)
        while len(self.history) < self.config.budget:
            suggestion = self._suggest_next()
            result = self.oracle.evaluate(suggestion.candidate)
            record = self._build_record(len(self.history) + 1, suggestion, result)
            self.history.append(record)
            self._write_results()
            if result.success:
                logfire.info(
                    'Evaluation complete',
                    evaluation_index=record['evaluation_index'],
                    strategy=record['strategy'],
                    yield_value=record['objective_values']['yield'],
                )
            else:
                logfire.info(
                    'Evaluation failed',
                    evaluation_index=record['evaluation_index'],
                    strategy=record['strategy'],
                    failure_reason=record['failure_reason'],
                )
        summary = self._summary()
        self._write_results(summary)
        return summary

    def _suggest_next(self):
        successful = [r for r in self.history if r['status'] == 'success']
        observed_candidates = [self._candidate_from_record(r) for r in successful]
        observed_yields = [float(r['objective_values']['yield']) for r in successful]
        seen_keys = {self._candidate_from_record(r).key() for r in self.history}
        return self.optimizer.suggest(observed_candidates, observed_yields, seen_keys)

    @staticmethod
    def _candidate_from_record(record: Dict[str, Any]) -> Candidate:
        pv = record['parameter_values']
        return Candidate(
            base=pv['base'],
            ligand=pv['ligand'],
            solvent=pv['solvent'],
            concentration=float(pv['concentration']),
            temperature_c=int(pv['temperature_c']),
        )

    def _build_record(self, evaluation_index: int, suggestion, result) -> Dict[str, Any]:
        record: Dict[str, Any] = {
            'evaluation_index': evaluation_index,
            'batch_index': evaluation_index,
            'batch_size': 1,
            'parameter_values': suggestion.candidate.to_parameter_values(),
            'status': result.status,
            'objective_values': {'yield': float(result.objective_value)} if result.success else {},
            'failure_reason': result.failure_reason,
            'strategy': suggestion.strategy,
            'acquisition_value': suggestion.acquisition,
            'objective_unit': OBJECTIVE_UNIT,
        }
        return record

    def _summary(self) -> Dict[str, Any]:
        successes = [r for r in self.history if r['status'] == 'success']
        best_record = max(successes, key=lambda r: r['objective_values']['yield']) if successes else None
        return {
            'cache_buster_nonce': NONCE,
            'case_id': CASE_ID,
            'objective_name': OBJECTIVE_NAME,
            'objective_direction': OBJECTIVE_DIRECTION,
            'objective_unit': OBJECTIVE_UNIT,
            'attempted_evaluations': len(self.history),
            'completed_evaluations': len(successes),
            'successful_evaluations': len(successes),
            'failed_evaluations': len(self.history) - len(successes),
            'best_objective_value': float(best_record['objective_values']['yield']) if best_record else None,
            'best_parameters': best_record['parameter_values'] if best_record else None,
            'results': self.history,
        }

    def _write_results(self, summary: Dict[str, Any] | None = None) -> None:
        payload = summary or self._summary()
        self.results_path.write_text(json.dumps(payload, indent=2))
