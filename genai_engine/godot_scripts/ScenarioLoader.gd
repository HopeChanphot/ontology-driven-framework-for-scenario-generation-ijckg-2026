## ScenarioLoader.gd — Godot 4.4 Autoload Singleton (v2 — Dual Variants)
## ======================================================================
## Phase 7: Runtime Matching Engine
## Loads the JSON scenario pool and serves scenarios matching
## the current player persona path with real/fake variant support.
##
## Pool structure (v2):
##   {persona_path_id} → {channel} → {variant} → {llm_source} → [scenarios]
##
## Setup: Project → Project Settings → Autoload → Add as "ScenarioLoader"
##
## Dependencies: Reads from GameState autoload:
##   GameState.role        — "finance" | "IT" | "management" | "other"
##   GameState.knowledge   — "beginner" | "intermediate" | "expert"
##   GameState.difficulty  — 1-10 (int, placement score)
##   GameState.company     — company name (string)
##   GameState.dept        — department (string)
##   GameState.position    — job position (string)

extends Node

## ── Constants ──────────────────────────────────────────────
const POOL_PATH := "res://data/scenario_pool.json"

## ── State ──────────────────────────────────────────────────
var _pool: Dictionary = {}
var _loaded: bool = false
var _used_ids: Array[String] = []  ## Track used scenario IDs to avoid repeats

## ── Signals ────────────────────────────────────────────────
signal pool_loaded(count: int)
signal scenario_served(scenario: Dictionary)
signal no_scenario_available(persona_path_id: String, channel: String, variant: String)


## ── Lifecycle ──────────────────────────────────────────────

func _ready() -> void:
	_load_pool()


## ── Pool Loading ───────────────────────────────────────────

func _load_pool() -> void:
	if not FileAccess.file_exists(POOL_PATH):
		push_warning("ScenarioLoader: Pool file not found at %s" % POOL_PATH)
		return

	var file := FileAccess.open(POOL_PATH, FileAccess.READ)
	if file == null:
		push_error("ScenarioLoader: Cannot open %s — error %d" % [POOL_PATH, FileAccess.get_open_error()])
		return

	var json_text := file.get_as_text()
	file.close()

	var json := JSON.new()
	var err := json.parse(json_text)
	if err != OK:
		push_error("ScenarioLoader: JSON parse error at line %d: %s" % [json.get_error_line(), json.get_error_message()])
		return

	_pool = json.data
	_loaded = true

	var count := _count_scenarios()
	print("ScenarioLoader: Loaded %d scenarios from pool" % count)
	pool_loaded.emit(count)


func _count_scenarios() -> int:
	var count := 0
	for pid in _pool:
		for ch in _pool[pid]:
			for variant in _pool[pid][ch]:
				for llm in _pool[pid][ch][variant]:
					count += (_pool[pid][ch][variant][llm] as Array).size()
	return count


## ── Public API ─────────────────────────────────────────────

## Build the persona path ID from current GameState
func get_persona_path_id() -> String:
	return "%s_%s_%d" % [GameState.role, GameState.knowledge, GameState.difficulty]


## Get a random scenario for the current persona + channel + variant
## variant: "fake" for scam scenarios, "real" for legitimate scenarios
func get_scenario(channel: String, variant: String = "fake") -> Dictionary:
	if not _loaded:
		push_warning("ScenarioLoader: Pool not loaded yet")
		no_scenario_available.emit("unknown", channel, variant)
		return {}

	var pid := get_persona_path_id()
	return get_scenario_for_path(pid, channel, variant)


## Get a random pair (one fake + one real) for gameplay comparison
func get_scenario_pair(channel: String) -> Dictionary:
	var fake := get_scenario(channel, "fake")
	var real := get_scenario(channel, "real")
	return {"fake": fake, "real": real}


## Get a scenario for a specific persona path + channel + variant
func get_scenario_for_path(persona_path_id: String, channel: String, variant: String = "fake") -> Dictionary:
	if not _pool.has(persona_path_id):
		push_warning("ScenarioLoader: No scenarios for path '%s'" % persona_path_id)
		no_scenario_available.emit(persona_path_id, channel, variant)
		return {}

	var path_data: Dictionary = _pool[persona_path_id]
	if not path_data.has(channel):
		push_warning("ScenarioLoader: No '%s' scenarios for path '%s'" % [channel, persona_path_id])
		no_scenario_available.emit(persona_path_id, channel, variant)
		return {}

	if not path_data[channel].has(variant):
		push_warning("ScenarioLoader: No '%s' variant for path '%s/%s'" % [variant, persona_path_id, channel])
		no_scenario_available.emit(persona_path_id, channel, variant)
		return {}

	## Collect all scenarios across LLM sources for this channel + variant
	var candidates: Array[Dictionary] = []
	for llm_key in path_data[channel][variant]:
		for s in path_data[channel][variant][llm_key]:
			## Skip already-used scenarios
			if s.has("scenario_id") and s["scenario_id"] in _used_ids:
				continue
			candidates.append(s)

	if candidates.is_empty():
		## Reset used IDs if all exhausted, then retry
		_used_ids.clear()
		return get_scenario_for_path(persona_path_id, channel, variant)

	## Pick random scenario
	var chosen: Dictionary = candidates[randi() % candidates.size()]

	## Track usage
	if chosen.has("scenario_id"):
		_used_ids.append(chosen["scenario_id"])

	## Inject live persona context
	chosen["_persona"] = {
		"role": GameState.role,
		"knowledge": GameState.knowledge,
		"difficulty": GameState.difficulty,
		"company": GameState.company,
		"department": GameState.dept,
		"position": GameState.position,
	}

	scenario_served.emit(chosen)
	return chosen


## Get all available channels for current persona
func get_available_channels() -> Array[String]:
	var pid := get_persona_path_id()
	if not _pool.has(pid):
		return []
	return Array(_pool[pid].keys(), TYPE_STRING, &"", null)


## Get available variants for a path + channel
func get_available_variants(persona_path_id: String, channel: String) -> Array[String]:
	if not _pool.has(persona_path_id):
		return []
	if not _pool[persona_path_id].has(channel):
		return []
	return Array(_pool[persona_path_id][channel].keys(), TYPE_STRING, &"", null)


## Get scenario count for a specific path/channel/variant
func get_scenario_count(persona_path_id: String, channel: String, variant: String = "") -> int:
	if not _pool.has(persona_path_id):
		return 0
	if not _pool[persona_path_id].has(channel):
		return 0

	var count := 0
	var channel_data: Dictionary = _pool[persona_path_id][channel]

	if variant != "":
		## Count specific variant
		if not channel_data.has(variant):
			return 0
		for llm_key in channel_data[variant]:
			count += (channel_data[variant][llm_key] as Array).size()
	else:
		## Count all variants
		for v in channel_data:
			for llm_key in channel_data[v]:
				count += (channel_data[v][llm_key] as Array).size()

	return count


## Reset used-scenario tracking (e.g., on new game)
func reset_tracking() -> void:
	_used_ids.clear()


## Reload the pool from disk (e.g., after DDA adjustment)
func reload_pool() -> void:
	_pool.clear()
	_loaded = false
	_used_ids.clear()
	_load_pool()
