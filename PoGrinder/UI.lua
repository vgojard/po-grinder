local _, ns = ...
-- Étape 4 : fenêtre PoGrinder (onglets Zones / Objets, détail au survol, clic = carte)

local UI = {}
ns.UI = UI

local ROW_H, ROWS_MAX, WIDTH, HEIGHT = 34, 40, 460, 430
local frame, scroll, content, status
local rows, tabs = {}, {}
local mode = "zones"
local areaToMap

local function mapForArea(area)
  if not areaToMap then
    areaToMap = {}
    for map, a in pairs(ns.UiToArea or {}) do
      if not areaToMap[a] then areaToMap[a] = map end
    end
  end
  return areaToMap[area]
end

local function openMap(area)
  local map = mapForArea(area)
  if not map then return end
  if OpenWorldMap then
    OpenWorldMap(map)
  elseif WorldMapFrame then
    ShowUIPanel(WorldMapFrame)
    if WorldMapFrame.SetMapID then WorldMapFrame:SetMapID(map) end
  end
end

-- Tooltip détaillé d'une zone
local function zoneTooltip(owner, r)
  GameTooltip:SetOwner(owner, "ANCHOR_RIGHT")
  GameTooltip:AddLine(ns.ZoneName(r.area), 1, 0.82, 0)
  GameTooltip:AddDoubleLine("Estimation", ns.Money(r.estimate) .. "/h", 1, 1, 1, 1, 1, 1)
  if r.gather > 0 then
    GameTooltip:AddDoubleLine(string.format("  Récolte (%d nœuds)", r.nodes or 0), ns.Money(r.gather) .. "/h", 0.8, 0.8, 0.8, 1, 1, 1)
  end
  if r.mobs > 0 then
    GameTooltip:AddDoubleLine(string.format("  Mobs niv %d-%d", r.lo, r.hi), ns.Money(r.mobs) .. "/h", 0.8, 0.8, 0.8, 1, 1, 1)
  end
  if r.measured then
    GameTooltip:AddDoubleLine(string.format("Mesuré (%d min)", r.measuredMin), ns.Money(r.measured) .. "/h", 0.2, 1, 0.6, 0.2, 1, 0.6)
  end
  if r.drops and #r.drops > 0 then
    GameTooltip:AddLine(" ")
    GameTooltip:AddLine("Drops principaux (par kill) :", 0.7, 0.7, 0.7)
    for i = 1, math.min(#r.drops, 10), 2 do
      GameTooltip:AddDoubleLine("  " .. ns.ItemName(r.drops[i]), string.format("%.1f%%", r.drops[i + 1] * 100), 1, 1, 1, 0.8, 0.8, 0.8)
    end
  end
  GameTooltip:AddLine(" ")
  GameTooltip:AddLine("Clic : ouvrir la carte", 0.5, 0.5, 0.5)
  GameTooltip:Show()
end

local function itemTooltip(owner, r)
  GameTooltip:SetOwner(owner, "ANCHOR_RIGHT")
  local ok = pcall(GameTooltip.SetItemByID, GameTooltip, r.id)
  if not ok then GameTooltip:AddLine(ns.ItemName(r.id), 1, 1, 1) end
  GameTooltip:AddLine(" ")
  GameTooltip:AddDoubleLine("PoGrinder : " .. (r.p.bestSource or "?"), ns.Money(r.p.best), 0.2, 1, 0.6, 1, 1, 1)
  local zones = ns.FarmDB and ns.FarmDB[r.id]
  for i = 1, math.min(#(zones or {}), 4) do
    GameTooltip:AddLine("  " .. ns.FormatZone(zones[i]), 0.8, 0.8, 0.8, true)
  end
  GameTooltip:AddLine("Clic : carte de la meilleure zone", 0.5, 0.5, 0.5)
  GameTooltip:Show()
end

local function getRow(i)
  if rows[i] then return rows[i] end
  local b = CreateFrame("Button", nil, content)
  b:SetHeight(ROW_H)
  b:SetPoint("TOPLEFT", 0, -(i - 1) * ROW_H)
  b:SetPoint("RIGHT", content, "RIGHT", 0, 0)
  b:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight", "ADD")
  b.title = b:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  b.title:SetPoint("TOPLEFT", 6, -3)
  b.title:SetJustifyH("LEFT")
  b.value = b:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
  b.value:SetPoint("TOPRIGHT", -6, -3)
  b.sub = b:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  b.sub:SetPoint("TOPLEFT", 18, -18)
  b.sub:SetPoint("RIGHT", -6, 0)
  b.sub:SetJustifyH("LEFT")
  b.sub:SetWordWrap(false)
  b:SetScript("OnEnter", function(self)
    if not self.data then return end
    if mode == "zones" then zoneTooltip(self, self.data) else itemTooltip(self, self.data) end
  end)
  b:SetScript("OnLeave", function() GameTooltip:Hide() end)
  b:SetScript("OnClick", function(self)
    local d = self.data
    if not d then return end
    if mode == "zones" then
      openMap(d.area)
    else
      local z = ns.BestZone(d.id)
      if z then openMap(z[1]) end
    end
  end)
  rows[i] = b
  return b
end

local function fill(list, render)
  for i, b in ipairs(rows) do b:Hide(); b.data = nil end
  for i = 1, math.min(#list, ROWS_MAX) do
    local b = getRow(i)
    b.data = list[i]
    render(b, i, list[i])
    b:Show()
  end
  content:SetHeight(math.max(1, math.min(#list, ROWS_MAX) * ROW_H))
  scroll:SetVerticalScroll(0)
end

local function renderZones()
  local list, skills, level = ns.Zones.Rank()
  fill(list, function(b, i, r)
    b.title:SetText(i .. ". " .. ns.ZoneName(r.area))
    b.value:SetText("~" .. ns.Money(r.final) .. "/h")
    local parts = {}
    if r.gather > 0 then parts[#parts + 1] = "récolte " .. ns.Money(r.gather) end
    if r.mobs > 0 then parts[#parts + 1] = string.format("mobs %s (niv %d-%d)", ns.Money(r.mobs), r.lo, r.hi) end
    if r.measured then parts[#parts + 1] = "|cff33ff99mesuré|r" end
    if r.top then parts[#parts + 1] = "surtout : " .. ns.ItemName(r.top) end
    b.sub:SetText(table.concat(parts, "  ·  "))
  end)
  local metiers = not skills and "métiers non détectés"
    or ((skills.m and "minage " or "") .. (skills.h and "herboristerie" or ""))
  if metiers == "" then metiers = "sans métier de récolte" end
  status:SetText(string.format("Niveau %d · %s · %d kills/h · %d nœuds/h", level, metiers,
    ns.db.killsPerHour or ns.Zones.defaults.killsPerHour, ns.db.nodesPerHour or ns.Zones.defaults.nodesPerHour))
end

local function renderItems()
  local list = ns.TopItems()
  fill(list, function(b, i, r)
    b.title:SetText(i .. ". " .. ns.ItemName(r.id))
    b.value:SetText(ns.Money(r.p.best) .. " (" .. (r.p.bestSource or "?") .. ")")
    local z = ns.BestZone(r.id)
    b.sub:SetText(z and ns.FormatZone(z) or "zone inconnue")
  end)
  status:SetText(string.format("%d ressources avec un prix connu", #list))
end

function UI.Refresh()
  if not frame then return end
  for k, t in pairs(tabs) do
    if k == mode then t:LockHighlight() else t:UnlockHighlight() end
  end
  local ok, err = pcall(mode == "zones" and renderZones or renderItems)
  if not ok then
    status:SetText("|cffff4444Erreur :|r " .. tostring(err))
    ns.Print("|cffff4444Fenêtre :|r " .. tostring(err))
  end
end

local function build()
  frame = CreateFrame("Frame", "PoGrinderFrame", UIParent, "BasicFrameTemplateWithInset")
  frame:SetSize(WIDTH, HEIGHT)
  frame:SetPoint("CENTER")
  frame:SetFrameStrata("HIGH")
  frame:SetMovable(true)
  frame:EnableMouse(true)
  frame:RegisterForDrag("LeftButton")
  frame:SetScript("OnDragStart", frame.StartMoving)
  frame:SetScript("OnDragStop", function(self)
    self:StopMovingOrSizing()
    local p, _, rp, x, y = self:GetPoint()
    ns.db.framePos = { p, rp, x, y }
  end)
  frame:SetClampedToScreen(true)
  tinsert(UISpecialFrames, "PoGrinderFrame") -- Échap ferme la fenêtre

  local title = frame.TitleText or frame:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
  if not frame.TitleText then title:SetPoint("TOP", 0, -5) end
  title:SetText("PoGrinder")

  local function tab(key, label, x)
    local t = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
    t:SetSize(90, 22)
    t:SetPoint("TOPLEFT", x, -30)
    t:SetText(label)
    t:SetScript("OnClick", function() mode = key; UI.Refresh() end)
    tabs[key] = t
  end
  tab("zones", "Zones", 12)
  tab("items", "Objets", 106)

  local refresh = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
  refresh:SetSize(90, 22)
  refresh:SetPoint("TOPRIGHT", -12, -30)
  refresh:SetText("Actualiser")
  refresh:SetScript("OnClick", UI.Refresh)

  scroll = CreateFrame("ScrollFrame", nil, frame, "UIPanelScrollFrameTemplate")
  scroll:SetPoint("TOPLEFT", 12, -58)
  scroll:SetPoint("BOTTOMRIGHT", -32, 30)
  content = CreateFrame("Frame", nil, scroll)
  content:SetSize(WIDTH - 46, 1)
  scroll:SetScrollChild(content)

  status = frame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  status:SetPoint("BOTTOMLEFT", 14, 10)
  status:SetPoint("BOTTOMRIGHT", -14, 10)
  status:SetJustifyH("LEFT")

  local pos = ns.db and ns.db.framePos
  if pos then
    frame:ClearAllPoints()
    frame:SetPoint(pos[1], UIParent, pos[2], pos[3], pos[4])
  end
  frame:SetScript("OnShow", UI.Refresh)
  frame:Hide()
end

function UI.Toggle()
  if not frame then build() end
  if frame:IsShown() then frame:Hide() else frame:Show() end
end
