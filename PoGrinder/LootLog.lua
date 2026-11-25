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
local windowSources, windowDone  -- corps de la fenêtre de loot en cours
local lootActive, lootClosedAt, lastMoney = false, 0, nil

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

-- Objet gris (qualité médiocre) : on compte toujours son prix marchand
local GetQuality = C_Item and C_Item.GetItemQualityByID
local function isGray(link, itemID)
  if link and (link:find("|cff9d9d9d", 1, true) or link:find("|cnIQ0:", 1, true)) then return true end
  local q = GetQuality and GetQuality(itemID) or select(3, ns.GetItemInfo(itemID))
  return q == 0
end

local function itemValue(itemID, link)
  if isGray(link, itemID) then
    local ok, v = pcall(ns.Prices.Vendor, itemID)
    return ok and v or 0, true
  end
  local ok, p = pcall(ns.Prices.Get, itemID)
  return ok and p and p.best or 0, false
end

local function onLootOpened()
  if windowDone then return end   -- LOOT_READY puis LOOT_OPENED : une seule fois
  windowDone, lootActive = true, true
  tick()
  local now = time()
  for guid, s in pairs(seen) do
    if now - s.t > SEEN_TTL then seen[guid] = nil end
  end

  local touched = {} -- sources vues dans cette fenêtre : [guid] = key
  windowSources = {}
  for slot = 1, GetNumLootItems() do
    for i = 1, select("#", GetLootSourceInfo(slot)), 2 do
      local guid = select(i, GetLootSourceInfo(slot))
      local kind, id = parseGUID(guid)
      if kind == "n" and not (seen[guid] and seen[guid].money) then windowSources[guid] = id end
    end
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
              local v, gray = itemValue(itemID, link)
              z.value = z.value + qty * v
              if gray then z.gray = (z.gray or 0) + qty * v end
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
  lootActive, windowDone, lootClosedAt = false, false, GetTime()
  for _, s in pairs(seen) do s.closed = true end
end

-- Argent brut : tout gain d'argent pendant (ou juste après) une fenêtre de loot
-- est réparti à parts égales entre les corps de cette fenêtre.
local function onMoney()
  local now = GetMoney()
  local gained = lastMoney and (now - lastMoney) or 0
  lastMoney = now
  if gained <= 0 or not windowSources then return end
  if not lootActive and GetTime() - lootClosedAt > 1.5 then return end
  local n = 0
  for _ in pairs(windowSources) do n = n + 1 end
  if n == 0 then return end
  for guid, id in pairs(windowSources) do
    local e = log.money[id] or { corpses = 0, copper = 0 }
    log.money[id] = e
    e.copper = e.copper + gained / n
    seen[guid] = seen[guid] or { t = time(), items = {} }
    if not seen[guid].money then
      seen[guid].money = true
      e.corpses = e.corpses + 1
    end
  end
  if curMap then zoneEntry(curMap).value = zoneEntry(curMap).value + gained end
end

-- WoW Forever ferme COMBAT_LOG_EVENT_* aux addons (s'y inscrire fait bloquer l'addon).
-- On utilise l'événement PARTY_KILL (attaquant, cible), qui ne porte que des GUID.
local function onPartyKill(_, targetGUID)
  local kind, id = parseGUID(targetGUID)
  if kind == "n" then bump(log.kills, id) end
end

local f = CreateFrame("Frame")
f:RegisterEvent("PLAYER_LOGIN")
f:SetScript("OnEvent", function(_, event, ...)
  if event == "PLAYER_LOGIN" then
    PoGrinderLog = PoGrinderLog or {}
    log = PoGrinderLog
    log.version = 1
    log.kills = log.kills or {}
    log.loots = log.loots or {}
    log.zones = log.zones or {}
    log.money = log.money or {}  -- [npcID] = { corpses, copper }
    playerGUID = UnitGUID("player")
    tick()
    lastMoney = GetMoney()
    f:RegisterEvent("LOOT_READY")
    f:RegisterEvent("LOOT_OPENED")
    f:RegisterEvent("PLAYER_MONEY")
    f:RegisterEvent("LOOT_CLOSED")
    f:RegisterEvent("ZONE_CHANGED_NEW_AREA")
    f:RegisterEvent("PLAYER_LOGOUT")
    pcall(f.RegisterEvent, f, "PARTY_KILL")
  elseif event == "LOOT_READY" or event == "LOOT_OPENED" then
    local ok, err = pcall(onLootOpened)
    if not ok then ns.Print("|cffff4444LootLog :|r " .. tostring(err)) end
  elseif event == "LOOT_CLOSED" then
    onLootClosed()
  elseif event == "PLAYER_MONEY" then
    pcall(onMoney)
  elseif event == "PARTY_KILL" then
    pcall(onPartyKill, ...)
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
  local cop, nc = 0, 0
  for _, e in pairs(log.money) do cop, nc = cop + e.copper, nc + e.corpses end
  ns.Print(string.format("Journal : %d kills, %d sources fouillées, %s d'argent brut sur %d corps.", nk, nl, ns.Money(cop), nc))
  local rows = {}
  for map, z in pairs(log.zones) do
    if z.secs >= 300 then
      rows[#rows + 1] = { map = map, gph = z.value / z.secs * 3600, secs = z.secs,
                          gray = (z.gray or 0) / z.secs * 3600 }
    end
  end
  table.sort(rows, function(a, b) return a.gph > b.gph end)
  for i = 1, math.min(10, #rows) do
    local r = rows[i]
    local info = C_Map.GetMapInfo and C_Map.GetMapInfo(r.map)
    ns.Print(string.format("  %s : %s/h mesuré sur %d min (dont gris : %s/h)",
      info and info.name or ("carte #" .. r.map), ns.Money(r.gph), r.secs / 60, ns.Money(r.gray)))
  end
  if #rows == 0 then ns.Print("  Pas encore assez de temps de farm (5 min minimum par zone).") end
end
