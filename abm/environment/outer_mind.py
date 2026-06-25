from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import combinations
from typing import Iterable

from ..core.types import StudentState, StudentTrait


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass(frozen=True)
class OuterMindConfig:
    baseline_closeness: float = 0.03
    closeness_decay_per_hour: float = 0.006
    closeness_gain_per_hour: float = 0.10
    closeness_compatibility_weight: float = 0.65
    closeness_mirror_weight: float = 0.35
    closeness_gap_cooling_per_hour: float = 0.05
    social_contribution_gain_per_hour: float = 0.12
    social_return_gain_per_hour: float = 0.18
    social_contribution_decay_per_hour: float = 0.70
    social_return_decay_per_hour: float = 0.60
    social_energy_cost_per_hour: float = 0.05
    feedback_energy_threshold: float = 0.20
    extrinsic_decay_base_per_hour: float = 0.08
    extrinsic_exchange_rate_per_hour: float = 0.08
    burnout_base: float = 0.60
    wellbeing_update_rate_per_hour: float = 0.01
    max_social_partners_per_agent: int = 6


@dataclass(frozen=True)
class SocialTie:
    source_id: int
    target_id: int
    closeness: float


@dataclass(frozen=True)
class OuterMindDelta:
    relationship_changes: dict[tuple[int, int], float] = field(default_factory=dict)
    social_contribution_changes: dict[int, float] = field(default_factory=dict)
    social_return_changes: dict[int, float] = field(default_factory=dict)
    extrinsic_satisfaction_changes: dict[int, float] = field(default_factory=dict)
    wellbeing_changes: dict[int, float] = field(default_factory=dict)
    energy_changes: dict[int, float] = field(default_factory=dict)


class OuterMindDynamics:
    """Directed social-exchange equations for relationship and wellbeing dynamics."""

    def __init__(self, config: OuterMindConfig | None = None) -> None:
        self.config = config or OuterMindConfig()
        self._relationships: dict[tuple[int, int], float] = {}

    def ties(self) -> tuple[SocialTie, ...]:
        return tuple(
            SocialTie(source, target, closeness)
            for (source, target), closeness in sorted(self._relationships.items())
        )

    def relationship(self, source_id: int, target_id: int) -> float:
        return self._relationships.get(
            (source_id, target_id),
            self.config.baseline_closeness,
        )

    def closeness(self, source_id: int, target_id: int) -> float:
        return self.relationship(source_id, target_id)

    def set_relationship(self, source_id: int, target_id: int, *, closeness: float) -> None:
        self._relationships[(source_id, target_id)] = _clamp01(closeness)

    def advance(self, agents: Iterable[object], seconds: int) -> OuterMindDelta:
        hours = max(0, seconds) / 3600.0
        agent_list = list(agents)
        before_relationships = dict(self._relationships)
        before_states = {
            int(agent.unique_id): self._state_snapshot(agent.state, agent.trait)
            for agent in agent_list
        }

        partners_by_id = self._social_partners(agent_list, self.config.max_social_partners_per_agent)
        active_directed_keys = {
            (int(agent.unique_id), int(partner.unique_id))
            for agent in agent_list
            for partner in partners_by_id.get(int(agent.unique_id), [])
        }

        self._decay_relationships(active_directed_keys, hours)
        relationships_before_interaction = dict(self._relationships)
        self._decay_social_memory(agent_list, hours)

        for agent in agent_list:
            agent_id = int(agent.unique_id)
            partners = partners_by_id.get(agent_id, [])
            if partners:
                self._apply_social_exchange(agent, partners, hours, relationships_before_interaction)
            else:
                self._decay_extrinsic_satisfaction(agent.trait, agent.state, hours)
            self._update_wellbeing(agent.trait, agent.state, hours)

        self._apply_cognitive_dissonance(hours)
        return self._delta(agent_list, before_relationships, before_states)

    @staticmethod
    def compatibility(left: StudentTrait, right: StudentTrait) -> float:
        keys = set(left.interests) | set(right.interests)
        if not keys:
            return 0.0
        left_values = [max(0.0, left.interests.get(key, 0.0)) for key in keys]
        right_values = [max(0.0, right.interests.get(key, 0.0)) for key in keys]
        dot = sum(a * b for a, b in zip(left_values, right_values))
        left_norm = math.sqrt(sum(value * value for value in left_values))
        right_norm = math.sqrt(sum(value * value for value in right_values))
        if left_norm <= 0.0 or right_norm <= 0.0:
            return 0.0
        return _clamp01(dot / (left_norm * right_norm))

    def _apply_social_exchange(
        self,
        agent: object,
        partners: list[object],
        hours: float,
        relationships_before_interaction: dict[tuple[int, int], float],
    ) -> None:
        state: StudentState = agent.state
        trait: StudentTrait = agent.trait
        if not partners:
            return

        state.social_contribution = _clamp01(
            state.social_contribution + self.config.social_contribution_gain_per_hour * hours
        )
        state.energy = _clamp01(state.energy - self.config.social_energy_cost_per_hour * hours)

        interaction_hours = hours / len(partners)
        for partner in partners:
            self._update_relationship(agent, partner, interaction_hours, relationships_before_interaction)
            self._receive_feedback(agent, partner, interaction_hours)

        burnout = self.config.burnout_base * (1.0 - _clamp01(trait.personality.get("agreeableness", 0.5)))
        exchange = state.social_return - burnout * state.social_contribution
        state.extrinsic_satisfaction = _clamp01(
            state.extrinsic_satisfaction + self.config.extrinsic_exchange_rate_per_hour * exchange * hours
        )

    def _update_relationship(
        self,
        source: object,
        target: object,
        hours: float,
        relationships_before_interaction: dict[tuple[int, int], float],
    ) -> None:
        source_id = int(source.unique_id)
        target_id = int(target.unique_id)
        before_closeness = self._relationship_from(
            relationships_before_interaction,
            source_id,
            target_id,
        )
        reverse_closeness = self._relationship_from(
            relationships_before_interaction,
            target_id,
            source_id,
        )
        compatibility = self.compatibility(source.trait, target.trait)
        closeness_drive = _clamp01(
            self.config.closeness_compatibility_weight * compatibility
            + self.config.closeness_mirror_weight * reverse_closeness
        )
        closeness = _clamp01(
            before_closeness
            + (1.0 - before_closeness) * self.config.closeness_gain_per_hour * closeness_drive * hours
        )
        self._relationships[(source_id, target_id)] = closeness

    def _receive_feedback(self, agent: object, partner: object, hours: float) -> None:
        partner_state: StudentState = partner.state
        if partner_state.energy <= self.config.feedback_energy_threshold:
            return
        agent_state: StudentState = agent.state
        partner_agreeableness = _clamp01(partner.trait.personality.get("agreeableness", 0.5))
        reverse_closeness = self.closeness(int(partner.unique_id), int(agent.unique_id))
        agent_state.social_return = _clamp01(
            agent_state.social_return
            + self.config.social_return_gain_per_hour * partner_agreeableness * reverse_closeness * hours
        )

    def _decay_relationships(self, active_directed_keys: set[tuple[int, int]], hours: float) -> None:
        closeness_decay = math.exp(-self.config.closeness_decay_per_hour * hours)
        for key, closeness in list(self._relationships.items()):
            if key in active_directed_keys:
                continue
            self._relationships[key] = _clamp01(closeness * closeness_decay)

    def _apply_cognitive_dissonance(self, hours: float) -> None:
        if hours <= 0.0:
            return
        for source_id, target_id in list(self._relationships):
            closeness = self.relationship(source_id, target_id)
            reverse_closeness = self.closeness(target_id, source_id)
            gap = closeness - reverse_closeness
            if gap <= 0.0:
                continue
            cooled = _clamp01(closeness - self.config.closeness_gap_cooling_per_hour * gap * hours)
            self._relationships[(source_id, target_id)] = cooled

    def _relationship_from(
        self,
        relationships: dict[tuple[int, int], float],
        source_id: int,
        target_id: int,
    ) -> float:
        return relationships.get(
            (source_id, target_id),
            self.config.baseline_closeness,
        )

    def _decay_social_memory(self, agents: list[object], hours: float) -> None:
        contribution_decay = math.exp(-self.config.social_contribution_decay_per_hour * hours)
        return_decay = math.exp(-self.config.social_return_decay_per_hour * hours)
        for agent in agents:
            state: StudentState = agent.state
            state.social_contribution = _clamp01(state.social_contribution * contribution_decay)
            state.social_return = _clamp01(state.social_return * return_decay)

    def _decay_extrinsic_satisfaction(self, trait: StudentTrait, state: StudentState, hours: float) -> None:
        extraversion = _clamp01(trait.personality.get("extraversion", 0.5))
        decay = math.exp(-self.config.extrinsic_decay_base_per_hour * (1.0 + extraversion) * hours)
        state.extrinsic_satisfaction = _clamp01(state.extrinsic_satisfaction * decay)

    def _update_wellbeing(self, trait: StudentTrait, state: StudentState, hours: float) -> None:
        extraversion = _clamp01(trait.personality.get("extraversion", 0.5))
        extrinsic_weight = 0.25 + 0.50 * extraversion
        intrinsic_weight = 1.0 - extrinsic_weight
        target = _clamp01(
            intrinsic_weight * state.intrinsic_satisfaction
            + extrinsic_weight * state.extrinsic_satisfaction
        )
        blend = 1.0 - math.exp(-self.config.wellbeing_update_rate_per_hour * hours)
        trait.wellbeing = _clamp01(trait.wellbeing * (1.0 - blend) + target * blend)

    @staticmethod
    def _social_partners(agents: list[object], max_partners_per_agent: int = 6) -> dict[int, list[object]]:
        partners: dict[int, list[object]] = {}
        groups: dict[tuple[str | None, str | None], list[object]] = {}
        for agent in agents:
            context = agent.context
            if context.phase != "ACTIVITY":
                continue
            if context.current_action not in {"social", "eat", "exercise"}:
                continue
            groups.setdefault((context.target_region_id, context.current_action), []).append(agent)

        limit = max(0, int(max_partners_per_agent))
        for group in groups.values():
            ordered = sorted(group, key=lambda item: int(item.unique_id))
            size = len(ordered)
            if size <= 1:
                continue
            if limit <= 0 or size - 1 <= limit:
                for left, right in combinations(ordered, 2):
                    left_id = int(left.unique_id)
                    right_id = int(right.unique_id)
                    partners.setdefault(left_id, []).append(right)
                    partners.setdefault(right_id, []).append(left)
                continue

            half = max(1, limit // 2)
            for index, agent in enumerate(ordered):
                agent_id = int(agent.unique_id)
                selected: list[object] = []
                for offset in range(1, half + 1):
                    selected.append(ordered[(index - offset) % size])
                    selected.append(ordered[(index + offset) % size])
                if len(selected) < limit:
                    selected.append(ordered[(index + half + 1) % size])
                partners[agent_id] = selected[:limit]
        return partners

    @staticmethod
    def _same_social_place(left: object, right: object) -> bool:
        left_context = left.context
        right_context = right.context
        if left_context.phase != "ACTIVITY" or right_context.phase != "ACTIVITY":
            return False
        if left_context.target_region_id != right_context.target_region_id:
            return False
        if left_context.current_action != right_context.current_action:
            return False
        return left_context.current_action in {"social", "eat", "exercise"}

    @staticmethod
    def _state_snapshot(state: StudentState, trait: StudentTrait) -> tuple[float, float, float, float, float]:
        return (
            state.social_contribution,
            state.social_return,
            state.extrinsic_satisfaction,
            trait.wellbeing,
            state.energy,
        )

    def _delta(
        self,
        agents: list[object],
        before_relationships: dict[tuple[int, int], float],
        before_states: dict[int, tuple[float, float, float, float, float]],
    ) -> OuterMindDelta:
        relationship_changes: dict[tuple[int, int], float] = {}
        keys = set(before_relationships) | set(self._relationships)
        for key in keys:
            before_closeness = before_relationships.get(
                key,
                self.config.baseline_closeness,
            )
            after_closeness = self.relationship(*key)
            dc = after_closeness - before_closeness
            if dc != 0.0:
                relationship_changes[key] = dc

        contribution_changes: dict[int, float] = {}
        return_changes: dict[int, float] = {}
        extrinsic_changes: dict[int, float] = {}
        wellbeing_changes: dict[int, float] = {}
        energy_changes: dict[int, float] = {}
        for agent in agents:
            agent_id = int(agent.unique_id)
            before = before_states[agent_id]
            state: StudentState = agent.state
            trait: StudentTrait = agent.trait
            contribution_changes[agent_id] = state.social_contribution - before[0]
            return_changes[agent_id] = state.social_return - before[1]
            extrinsic_changes[agent_id] = state.extrinsic_satisfaction - before[2]
            wellbeing_changes[agent_id] = trait.wellbeing - before[3]
            energy_changes[agent_id] = state.energy - before[4]

        return OuterMindDelta(
            relationship_changes=relationship_changes,
            social_contribution_changes=contribution_changes,
            social_return_changes=return_changes,
            extrinsic_satisfaction_changes=extrinsic_changes,
            wellbeing_changes=wellbeing_changes,
            energy_changes=energy_changes,
        )
