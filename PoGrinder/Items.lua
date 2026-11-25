local _, ns = ...

function ns.ItemName(itemID)
  local name = ns.GetItemInfo(itemID)
  if not name then
    ns.RequestItem(itemID)
    return (ns.FarmNames and ns.FarmNames[itemID]) or ("item:" .. itemID)
  end
  return name
end

local GetAreaInfo = (C_Map and C_Map.GetAreaInfo) or GetAreaInfo
function ns.ZoneName(areaID)
  local name = GetAreaInfo and GetAreaInfo(areaID)
  return name or ("zone #" .. areaID)
end

-- Zone FarmDB : {areaID, pointsRécolte, dropsMobsAttendus, lvlMin, lvlMax, spawnsTauxInconnu, mesuré}
function ns.BestZone(itemID)
  local zones = ns.FarmDB and ns.FarmDB[itemID]
  return zones and zones[1]
end

function ns.FormatZone(z)
  local parts = { ns.ZoneName(z[1]) }
  if z[2] > 0 then parts[#parts + 1] = z[2] .. " points de récolte" end
  if z[3] >= 0.5 then
    parts[#parts + 1] = string.format("mobs ~%.1f drops/tour (niv %d-%d)", z[3], z[4], z[5])
  elseif z[2] == 0 and (z[6] or 0) > 0 then
    parts[#parts + 1] = string.format("%d mobs à taux inconnu (niv %d-%d)", z[6], z[4], z[5])
  end
  if z[7] == 1 then parts[#parts + 1] = "|cff33ff99mesuré|r" end
  return table.concat(parts, ", ")
end
