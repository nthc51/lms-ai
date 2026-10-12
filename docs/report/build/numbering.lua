-- Đánh số "CHƯƠNG n." cho tiêu đề cấp 1 và "n.m." / "n.m.k." cho cấp 2, 3; tiêu đề {.unnumbered} giữ nguyên.
-- Mỗi tiêu đề cấp 1 sang trang mới. Đánh số hình theo chương: "Hình n.k: ...".
local counters = {0, 0, 0}
local fig = 0
local pagebreak = pandoc.RawBlock('openxml', '<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

local function blocks(doc)
  local out = {}
  for _, b in ipairs(doc.blocks) do
    if b.t == 'Header' then
      if b.level == 1 then table.insert(out, pagebreak) end
      if not b.classes:includes('unnumbered') and b.level <= 3 then
        counters[b.level] = counters[b.level] + 1
        for l = b.level + 1, 3 do counters[l] = 0 end
        if b.level == 1 then fig = 0 end
        local prefix
        if b.level == 1 then
          prefix = 'CHƯƠNG ' .. counters[1] .. '. '
        else
          local parts = {}
          for l = 1, b.level do table.insert(parts, tostring(counters[l])) end
          prefix = table.concat(parts, '.') .. '. '
        end
        table.insert(b.content, 1, pandoc.Str(prefix))
      end
      table.insert(out, b)
    elseif b.t == 'Para' and #b.content == 1 and b.content[1].t == 'Image' then
      fig = fig + 1
      local img = b.content[1]
      local label = 'Hình ' .. counters[1] .. '.' .. fig .. ': '
      table.insert(img.caption, 1, pandoc.Str(label))
      table.insert(out, b)
    elseif b.t == 'Figure' then
      fig = fig + 1
      local label = 'Hình ' .. counters[1] .. '.' .. fig .. ': '
      local cap = b.caption.long[1]
      if cap and cap.content then table.insert(cap.content, 1, pandoc.Str(label)) end
      table.insert(out, b)
    else
      table.insert(out, b)
    end
  end
  doc.blocks = out
  return doc
end

return {{Pandoc = blocks}}
