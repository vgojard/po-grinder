local _, ns = ...
-- Journal de loot : compte les kills et ce que lâchent réellement mobs et nœuds,
-- et chronomètre le temps passé par zone pour calculer un or/heure mesuré.
-- tools/gen.py relit ces données (SavedVariables PoGrinderLog) pour corriger FarmDB.

local LootLog = {}
ns.LootLog = LootLog

local MAX_TICK = 600      -- au-delà, on considère que le joueur était AFK
local SEEN_TTL = 900      -- un corps rouvert dans ce délai n'est pas recompté

local log, playerGUID
local seen = {}           -- [guid] = { t = time, items = { [itemID] = true } }
local curMap, lastTick

local function parseGUID(guid)
  if not guid then return end
  local kind, _, _, _, _, id = strsplit("-", guid)
  id = tonumber(id)
  if not id then return end
  if kind == "Creature" or kind == "Vehicle" then return "n", id end
  if kind == "GameObject" then return "o", id end
end

local function bump(t, k, n)
  t[k] = (t[k] or 0) + (n or 1)
end

local function zoneEntry(map)
  log.zones[map] = log.zones[map] or { secs = 0, value = 0, items = {} }
  return log.zones[map]
end

local function currentMap()
  return C_Map and C_Map.GetBestMapForUnit and C_Map.GetBestMapForUnit("player")
end

-- Ajoute le temps écoulé à la zone courante (hors ville / auberge)
local function tick()
  local now = GetTime()
  if curMap and lastTick and not IsResting() then
    local dt = now - lastTick
    if dt > 0 and dt < MAX_TICK then
      zoneEntry(curMap).secs = zoneEntry(curMap).secs + dt
    end
  end
  lastTick = now
  curMap = currentMap() or curMap
end

local function itemValue(itemID)
  local ok, p = pcall(ns.Prices.Get, itemID)
  return ok and p and p.best or 0
end

local function onLootOpened()
  tick()
  local now = time()
  for guid, s in pairs(seen) do
    if now - s.t > SEEN_TTL then seen[guid] = nil end
  end

  local touched = {} -- sources vues dans cette fenêtre : [guid] = key
  for slot = 1, GetNumLootItems() do
    local link = GetLootSlotLink(slot)
    local itemID = link and tonumber(link:match("item:(%d+)"))
    if itemID then
      local src = { GetLootSourceInfo(slot) }
      for i = 1, #src, 2 do
        local guid, qty = src[i], tonumber(src[i + 1]) or 1
        local kind, id = parseGUID(guid)
        if kind then
          local s = seen[guid]
          local prefix = kind
          if s and s.items[itemID] then
            prefix = nil -- déjà compté (corps rouvert)
          elseif s and s.closed and kind == "n" then
            prefix = "s" -- corps déjà fouillé puis rouvert : dépeçage, minage, herboristerie
          end
          if prefix then
            local key = prefix .. ":" .. id
            local e = log.loots[key] or { opens = 0, items = {} }
            log.loots[key] = e
            bump(e.items, itemID, qty)
            if not touched[guid] then
              touched[guid] = key
              e.opens = e.opens + 1
            end
            if curMap then
              local z = zoneEntry(curMap)
              bump(z.items, itemID, qty)
              z.value = z.value + qty * itemValue(itemID)
            end
            seen[guid] = seen[guid] or { t = now, items = {} }
            seen[guid].items[itemID] = true
          end
        end
      end
    end
  end
end

local function onLootClosed()
  for _, s in pairs(seen) do s.closed = true end
end

local function onCombatLog()
  if not CombatLogGetCurrentEventInfo then return end
  local _, sub, _, srcGUID, _, _, _, dstGUID = CombatLogGetCurrentEventInfo()
  if sub ~= "PARTY_KILL" then return end
  if srcGUID ~= playerGUID and srcGUID ~= UnitGUID("pet") then return end
  local kind, id = parseGUID(dstGUID)
  if kind == "n" then bump(log.kills, id) end
end

local f = CreateFrame("Frame")
f:RegisterEvent("PLAYER_LOGIN")
f:SetScript("OnEvent", function(_, event)
  if event == "PLAYER_LOGIN" then
    PoGrinderLog = PoGrinderLog or {}
    log = PoGrinderLog
    log.version = 1
    log.kills = log.kills or {}
    log.loots = log.loots or {}
    log.zones = log.zones or {}
    playerGUID = UnitGUID("player")
    tick()
    f:RegisterEvent("LOOT_OPENED")
    f:RegisterEvent("LOOT_CLOSED")
    f:RegisterEvent("ZONE_CHANGED_NEW_AREA")
    f:RegisterEvent("PLAYER_LOGOUT")
    pcall(f.RegisterEvent, f, "COMBAT_LOG_EVENT_UNFILTERED")
  elseif event == "LOOT_OPENED" then
    local ok, err = pcall(onLootOpened)
    if not ok and ns.db and ns.db.debug then ns.Print("LootLog : " .. tostring(err)) end
  elseif event == "LOOT_CLOSED" then
    onLootClosed()
  elseif event == "COMBAT_LOG_EVENT_UNFILTERED" then
    pcall(onCombatLog)
  else -- changement de zone, déconnexion
    tick()
  end
end)

-- Résumé pour /pogrind log
function LootLog.Report()
  if not log then return end
  tick()
  local nk, nl = 0, 0
  for _, n in pairs(log.kills) do nk = nk + n end
  for _, e in pairs(log.loots) do nl = nl + e.opens end
  ns.Print(string.format("Journal : %d kills, %d sources fouillées.", nk, nl))
  local rows = {}
  for map, z in pairs(log.zones) do
    if z.secs >= 300 then
      rows[#rows + 1] = { map = map, gph = z.value / z.secs * 3600, secs = z.secs }
    end
  end
  table.sort(rows, function(a, b) return a.gph > b.gph end)
  for i = 1, math.min(10, #rows) do
    local r = rows[i]
    local info = C_Map.GetMapInfo and C_Map.GetMapInfo(r.map)
    ns.Print(string.format("  %s : %s/h mesuré sur %d min",
      info and info.name or ("carte #" .. r.map), ns.Money(r.gph), r.secs / 60))
  end
  if #rows == 0 then ns.Print("  Pas encore assez de temps de farm (5 min minimum par zone).") end
end
