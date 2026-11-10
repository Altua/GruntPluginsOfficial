// src/precise-geometry.mjs
var EPSILON = 1e-7;
function shapeForRegion(region) {
  if (region.polygon) return ["path", { d: region.polygon.rings.map((ring) => `M ${ring.map((p) => `${p.x} ${p.y}`).join(" L ")} Z`).join(" "), "fill-rule": region.polygon.fillRule }];
  if (region.sector) return ["path", { d: sectorPath(region.sector), "fill-rule": "evenodd" }];
  if (region.path) return ["path", { d: region.path.data, transform: `translate(${region.path.translateX} ${region.path.translateY}) scale(${region.path.scale})` }];
  return ["rect", { ...region.rect }];
}
function containsRegion(region, x, y) {
  const b = region.rect;
  const inside = x >= b.x && y >= b.y && x <= b.x + b.width && y <= b.y + b.height;
  if (region.clipToRect && !inside) return false;
  if (region.sector) return sectorContainsPoint(region.sector, x, y);
  if (region.polygon) return polygonContainsPoint(region.polygon, x, y);
  return inside;
}
var radians = (degrees) => degrees * Math.PI / 180;
var normalizeAngle = (degrees) => (degrees % 360 + 360) % 360;
function isInteractionPath(value) {
  if (!value || typeof value !== "object")
    return false;
  const path = value;
  if (typeof path.data !== "string" || path.data.length === 0 || path.data.length > 1e5 || ![path.translateX, path.translateY, path.scale].every((n) => typeof n === "number" && Number.isFinite(n)) || path.scale <= 0)
    return false;
  const tokens = path.data.trim().match(/[MLC]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?/g);
  if (!tokens || tokens[0] !== "M" || tokens.join("") !== path.data.replace(/\s/g, ""))
    return false;
  for (let i = 0; i < tokens.length; ) {
    const command = tokens[i++];
    const count = command === "C" ? 6 : command === "M" || command === "L" ? 2 : 0;
    if (!count || i + count > tokens.length)
      return false;
    for (let j = 0; j < count; j++)
      if (!Number.isFinite(Number(tokens[i++])))
        return false;
  }
  return true;
}
function isInteractionSector(value) {
  if (!value || typeof value !== "object")
    return false;
  const sector = value;
  return [sector.centerX, sector.centerY, sector.innerRadius, sector.outerRadius, sector.startAngle, sector.sweepAngle].every((part) => typeof part === "number" && Number.isFinite(part)) && [
    sector.centerX - sector.outerRadius,
    sector.centerX + sector.outerRadius,
    sector.centerY - sector.outerRadius,
    sector.centerY + sector.outerRadius
  ].every(Number.isFinite) && sector.innerRadius >= 0 && sector.outerRadius > sector.innerRadius && Math.abs(sector.sweepAngle) > 0 && Math.abs(sector.sweepAngle) <= 360;
}
function isInteractionPolygon(value) {
  if (!value || typeof value !== "object")
    return false;
  const polygon = value;
  return (polygon.fillRule === "evenodd" || polygon.fillRule === "nonzero") && Array.isArray(polygon.rings) && polygon.rings.length > 0 && polygon.rings.length <= 1e3 && polygon.rings.every((ring) => Array.isArray(ring) && ring.length >= 3) && polygon.rings.reduce((count, ring) => count + ring.length, 0) <= 1e4 && polygon.rings.every((ring) => ring.every((p) => p && typeof p.x === "number" && typeof p.y === "number" && Number.isFinite(p.x) && Number.isFinite(p.y) && Math.abs(p.x) <= 1e12 && Math.abs(p.y) <= 1e12));
}
function polygonContainsPoint(polygon, x, y) {
  if (!isInteractionPolygon(polygon) || !Number.isFinite(x) || !Number.isFinite(y))
    return false;
  let winding = 0;
  for (const ring of polygon.rings)
    for (let i = 0; i < ring.length; i++) {
      const a = ring[i];
      const b = ring[(i + 1) % ring.length];
      const cross = (b.x - a.x) * (y - a.y) - (x - a.x) * (b.y - a.y);
      if (Math.abs(cross) <= EPSILON * Math.max(1, Math.hypot(b.x - a.x, b.y - a.y)) && x >= Math.min(a.x, b.x) - EPSILON && x <= Math.max(a.x, b.x) + EPSILON && y >= Math.min(a.y, b.y) - EPSILON && y <= Math.max(a.y, b.y) + EPSILON)
        return true;
      if (a.y <= y && b.y > y && cross > 0)
        winding++;
      if (a.y > y && b.y <= y && cross < 0)
        winding--;
    }
  return polygon.fillRule === "evenodd" ? Math.abs(winding) % 2 === 1 : winding !== 0;
}
function sectorContainsPoint(sector, x, y) {
  if (!isInteractionSector(sector) || !Number.isFinite(x) || !Number.isFinite(y))
    return false;
  const dx = x - sector.centerX;
  const dy = y - sector.centerY;
  const distance = Math.hypot(dx, dy);
  if (distance < sector.innerRadius || distance > sector.outerRadius)
    return false;
  if (Math.abs(sector.sweepAngle) >= 360 - EPSILON)
    return true;
  if (distance === 0 && sector.innerRadius === 0)
    return true;
  const angle = Math.atan2(dy, dx) * 180 / Math.PI;
  const progress = sector.sweepAngle > 0 ? normalizeAngle(angle - normalizeAngle(sector.startAngle)) : normalizeAngle(normalizeAngle(sector.startAngle) - angle);
  return progress <= Math.abs(sector.sweepAngle) + EPSILON;
}
function polarPoint(sector, radius, angle) {
  return `${sector.centerX + radius * Math.cos(radians(angle))} ${sector.centerY + radius * Math.sin(radians(angle))}`;
}
function sectorPath(sector) {
  if (!isInteractionSector(sector))
    return "";
  const { innerRadius, outerRadius, sweepAngle } = sector;
  const startAngle = normalizeAngle(sector.startAngle);
  const endAngle = startAngle + sweepAngle;
  const clockwise = sweepAngle > 0 ? 1 : 0;
  const reverse = clockwise ? 0 : 1;
  const arc = (radius, angle, large2, direction) => `A ${radius} ${radius} 0 ${large2} ${direction} ${polarPoint(sector, radius, angle)}`;
  if (Math.abs(sweepAngle) >= 360 - EPSILON) {
    const middle = startAngle + sweepAngle / 2;
    const outer2 = `M ${polarPoint(sector, outerRadius, startAngle)} ${arc(outerRadius, middle, 0, clockwise)} ${arc(outerRadius, endAngle, 0, clockwise)} Z`;
    if (innerRadius === 0)
      return outer2;
    return `${outer2} M ${polarPoint(sector, innerRadius, startAngle)} ${arc(innerRadius, startAngle - sweepAngle / 2, 0, reverse)} ${arc(innerRadius, startAngle - sweepAngle, 0, reverse)} Z`;
  }
  const large = Math.abs(sweepAngle) > 180 ? 1 : 0;
  const outer = `M ${polarPoint(sector, outerRadius, startAngle)} ${arc(outerRadius, endAngle, large, clockwise)}`;
  return innerRadius === 0 ? `${outer} L ${sector.centerX} ${sector.centerY} Z` : `${outer} L ${polarPoint(sector, innerRadius, endAngle)} ${arc(innerRadius, startAngle, large, reverse)} Z`;
}

// src/interaction-data.mjs
var fail = (message) => {
  throw new Error(message);
};
var assert = (condition, message = "Invalid interaction data") => {
  if (!condition) fail(message);
};
var record = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
var bytes = (value) => new TextEncoder().encode(value).byteLength;
var INTERACTION_LIMIT = Object.freeze({ bytes: 1024 * 1024, objects: 50, regions: 2e4, components: 50, cells: 2e5, text: 2e3, series: 1e4 });
var KINDS = /* @__PURE__ */ new Set(["object", "series", "category", "datum", "point", "cell", "group", "gantt", "shape"]);
var SERIES_TYPES = /* @__PURE__ */ new Set(["segment", "line", "area", "bubble", "slice", "dumbbell", "mekkoSegment", "waterfallSegment"]);
var POINT_TYPES = /* @__PURE__ */ new Set(["line", "area", "dumbbell", "bubble"]);
var REGION_FIELDS = ["kind", "rect", "seriesKey", "seriesIndex", "categoryKey", "categoryIndex", "dataPointKey", "rowIndex", "columnIndex", "xCategoryIndex", "yCategoryIndex"];
var INDEX_FIELDS = ["seriesIndex", "categoryIndex", "rowIndex", "columnIndex", "xCategoryIndex", "yCategoryIndex"];
var KEY_FIELDS = ["seriesKey", "categoryKey", "dataPointKey"];
var PRECISE_FIELDS = ["sector", "polygon", "clipToRect", "resolvedValue", "role", "targetObjectKey", "groupKey", "groupLabel", "groupSize", "gantt", "shape"];
var hex32 = (value) => typeof value === "string" && /^[0-9a-f]{32}$/.test(value);
var colorRe = /^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;
var localeRe = /^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/;
var finite = (value) => typeof value === "number" && Number.isFinite(value) && Math.abs(value) <= 1e7;
var index = (value) => Number.isInteger(value) && value >= 0 && value <= 1e6;
var normalizeKey = (value) => typeof value === "string" ? value.toLowerCase().replaceAll("-", "") : "";
function rect(value) {
  assert(record(value) && Object.keys(value).length === 4 && ["x", "y", "width", "height"].every((k) => finite(value[k])), "Invalid interaction rectangle");
  return { x: value.x, y: value.y, width: value.width, height: value.height };
}
function parseViewBox(text2) {
  const vb = String(text2 ?? "").trim().split(/[\s,]+/).map(Number);
  return vb.length === 4 && vb.every(Number.isFinite) && vb[2] > 0 && vb[3] > 0 ? { x: vb[0], y: vb[1], width: vb[2], height: vb[3] } : null;
}
var near = (a, b) => Math.abs(a - b) <= Math.max(50001e-9, 1e-6 * Math.max(1, Math.abs(a), Math.abs(b)));
var sameRect = (a, b) => ["x", "y", "width", "height"].every((k) => near(a[k], b[k]));
function objectViewports(root) {
  const viewports = [];
  for (const child of Array.from(root.childNodes ?? [])) {
    if (child.nodeType !== 1 || child.localName !== "g") continue;
    const elements = Array.from(child.childNodes ?? []).filter((n) => n.nodeType === 1);
    if (elements.length === 1 && elements[0].localName === "svg") viewports.push({ wrapper: child, svg: elements[0] });
  }
  return viewports;
}
function validRegion(value) {
  assert(record(value) && KINDS.has(value.kind), "Unsupported interaction region");
  const out = { kind: value.kind, rect: rect(value.rect) };
  assert(out.rect.width > 0 && out.rect.height > 0, "Degenerate interaction region");
  for (const k of INDEX_FIELDS) if (value[k] !== void 0 && value[k] !== null) {
    assert(index(value[k]), "Invalid interaction index");
    out[k] = value[k];
  }
  for (const k of KEY_FIELDS) if (value[k] !== void 0 && value[k] !== null) {
    assert(hex32(value[k]), "Invalid interaction key");
    out[k] = value[k];
  }
  if (value.sector != null) {
    assert(isInteractionSector(value.sector), "Invalid interaction sector");
    const s = value.sector;
    out.sector = { centerX: s.centerX, centerY: s.centerY, innerRadius: s.innerRadius, outerRadius: s.outerRadius, startAngle: s.startAngle, sweepAngle: s.sweepAngle };
  }
  if (value.polygon != null) {
    assert(isInteractionPolygon(value.polygon), "Invalid interaction polygon");
    out.polygon = { rings: value.polygon.rings.map((r) => r.map((p) => ({ x: p.x, y: p.y }))), fillRule: value.polygon.fillRule };
  }
  if (value.clipToRect != null) {
    assert(typeof value.clipToRect === "boolean", "Invalid contour clip");
    out.clipToRect = value.clipToRect;
  }
  if (value.resolvedValue != null) {
    assert(typeof value.resolvedValue === "number" && Number.isFinite(value.resolvedValue), "Invalid rendered value");
    out.resolvedValue = value.resolvedValue;
  }
  if (value.role != null) {
    assert(value.role === "legend", "Invalid interaction role");
    out.role = value.role;
  }
  if (value.targetObjectKey != null) {
    const k = normalizeKey(value.targetObjectKey);
    assert(hex32(k), "Invalid target object");
    out.targetObjectKey = k;
  }
  if (value.groupKey != null) {
    assert(hex32(value.groupKey), "Invalid group key");
    out.groupKey = value.groupKey;
  }
  if (value.groupLabel != null) {
    assert(typeof value.groupLabel === "string" && value.groupLabel.length <= INTERACTION_LIMIT.text, "Invalid group label");
    out.groupLabel = value.groupLabel;
  }
  if (value.groupSize != null) {
    assert(index(value.groupSize), "Invalid group size");
    out.groupSize = value.groupSize;
  }
  for (const field of ["gantt", "shape"]) if (value[field] != null) {
    const item = value[field], keys = field === "gantt" ? ["elementKey", "elementType", "label", "start", "end"] : ["elementKey", "elementType", "label"];
    assert(record(item) && Object.keys(item).every((k) => keys.includes(k)) && keys.every((k) => typeof item[k] === "string" && item[k].length <= INTERACTION_LIMIT.text), "Invalid element identity");
    if (field === "gantt") assert(hex32(item.elementKey) && ["bar", "process", "milestone"].includes(item.elementType) && [item.start, item.end].every((d) => /^\d{4}-\d{2}-\d{2}$/.test(d)), "Invalid timeline element");
    out[field] = Object.fromEntries(keys.map((k) => [k, item[k]]));
  }
  if (out.kind === "gantt") assert(out.gantt, "Missing timeline identity");
  if (out.kind === "shape") assert(out.shape, "Missing shape identity");
  if (out.kind === "group") assert(out.groupKey, "Missing group identity");
  if (out.kind === "datum") assert(out.seriesIndex !== void 0 && out.categoryIndex !== void 0, "Datum region without identity");
  if (out.kind === "category") assert(out.categoryIndex !== void 0, "Category region without identity");
  if (out.kind === "cell") assert(out.rowIndex !== void 0 && out.columnIndex !== void 0, "Cell region without identity");
  if (out.kind === "series") assert(out.seriesIndex !== void 0, "Series region without identity");
  return out;
}
function validOutline(value) {
  assert(record(value) && index(value.seriesIndex) && isInteractionPath(value.path), "Invalid series outline");
  const out = { rect: rect(value.rect), seriesIndex: value.seriesIndex, path: { data: value.path.data, translateX: value.path.translateX, translateY: value.path.translateY, scale: value.path.scale } };
  if (value.seriesKey != null) {
    assert(hex32(value.seriesKey), "Invalid outline series key");
    out.seriesKey = value.seriesKey;
  }
  return out;
}
function validCells(values, formats) {
  assert(Array.isArray(values) && values.length <= INTERACTION_LIMIT.cells, "Invalid interaction cell values");
  let count = 0;
  for (const row of values) {
    assert(Array.isArray(row), "Invalid interaction cell row");
    count += row.length;
    assert(count <= INTERACTION_LIMIT.cells, "Interaction data cell limit exceeded");
    for (const v of row) assert(v === null || typeof v === "boolean" || typeof v === "number" && Number.isFinite(v) || typeof v === "string" && v.length <= INTERACTION_LIMIT.text, "Unsupported cell value");
  }
  if (formats !== void 0) {
    assert(Array.isArray(formats) && formats.length <= values.length, "Invalid interaction number formats");
    for (const row of formats) {
      assert(Array.isArray(row), "Invalid interaction number formats");
      for (const f of row) assert(f === null || typeof f === "string" && f.length <= 255, "Invalid number format");
    }
  }
}
function validateComponent(c) {
  assert(record(c) && (c.type === "chart" || c.type === "table") && hex32(c.key), "Invalid interaction component");
  assert(Object.keys(c).every((k) => ["type", "key", "locale", "plotType", "primaryOrientation", "seriesDirection", "defaultSeriesType", "series", "categories", "values", "numberFormats"].includes(k)), "Unsupported interaction component field");
  if (c.primaryOrientation !== void 0) assert(["x", "y"].includes(c.primaryOrientation), "Invalid plot orientation");
  validCells(c.values, c.numberFormats);
  if (c.locale !== void 0) assert(typeof c.locale === "string" && localeRe.test(c.locale), "Invalid locale");
  if (c.seriesDirection !== void 0) assert(c.seriesDirection === "rows" || c.seriesDirection === "columns", "Invalid series direction");
  if (c.defaultSeriesType !== void 0) assert(SERIES_TYPES.has(c.defaultSeriesType), "Invalid series type");
  if (c.plotType !== void 0) assert(typeof c.plotType === "string" && /^[a-z]{1,32}$/.test(c.plotType), "Invalid plot type");
  if (c.series !== void 0) {
    assert(Array.isArray(c.series) && c.series.length <= INTERACTION_LIMIT.series, "Invalid series items");
    for (const s of c.series) {
      assert(record(s) && index(s.recordIndex) && Object.keys(s).every((k) => ["recordIndex", "key", "seriesType", "color", "visible"].includes(k)), "Invalid series item");
      if (s.key !== void 0) assert(hex32(s.key), "Invalid series key");
      if (s.seriesType !== void 0) assert(SERIES_TYPES.has(s.seriesType), "Invalid series type");
      if (s.color !== void 0) assert(colorRe.test(s.color), "Invalid series color");
      if (s.visible !== void 0) assert(s.visible === false, "Invalid series visibility");
    }
  }
  if (c.categories !== void 0) {
    assert(Array.isArray(c.categories) && c.categories.length <= INTERACTION_LIMIT.series, "Invalid category items");
    for (const k of c.categories) {
      assert(record(k) && index(k.recordIndex) && Object.keys(k).every((f) => ["recordIndex", "key"].includes(f)), "Invalid category item");
      if (k.key !== void 0) assert(hex32(k.key), "Invalid category key");
    }
  }
}
function validateInteraction(interaction, root) {
  assert(record(interaction) && interaction.version === 1 && interaction.source === "data-elements" && Array.isArray(interaction.objects) && Array.isArray(interaction.components) && Object.keys(interaction).length === 4, "Unsupported interaction snapshot");
  assert(interaction.objects.length <= INTERACTION_LIMIT.objects && interaction.components.length <= INTERACTION_LIMIT.components, "Interaction object limit exceeded");
  const viewports = objectViewports(root);
  assert(viewports.length === interaction.objects.length, "Interaction objects do not match the composed SVG");
  let regions = 0;
  interaction.objects.forEach((o, i) => {
    assert(record(o) && hex32(o.key) && typeof o.type === "string" && o.type.length <= 100 && Array.isArray(o.regions) && Object.keys(o).every((k) => ["key", "type", "viewBox", "regions", "seriesOutlines"].includes(k)), "Invalid interaction object");
    const viewBox = rect(o.viewBox), actual = parseViewBox(viewports[i].svg.getAttribute("viewBox"));
    assert(actual && sameRect(actual, viewBox), "Interaction coordinate space differs from the rendered object");
    const declared = viewports[i].wrapper.getAttribute("data-grunt-object");
    assert(!declared || normalizeKey(declared) === o.key, "Interaction object identity mismatch");
    regions += o.regions.length;
    assert(regions <= INTERACTION_LIMIT.regions, "Interaction region limit exceeded");
    for (const r of o.regions) {
      assert(!("hitId" in r), "Response-local hit IDs are not retained");
      assert(Object.keys(r).every((k) => REGION_FIELDS.includes(k) || PRECISE_FIELDS.includes(k)), "Unsupported retained region field");
      validRegion(r);
    }
    if (o.seriesOutlines !== void 0) {
      assert(Array.isArray(o.seriesOutlines) && o.seriesOutlines.length <= INTERACTION_LIMIT.series, "Invalid series outlines");
      for (const line of o.seriesOutlines) validOutline(line);
    }
  });
  assert(new Set(interaction.objects.map((o) => o.key)).size === interaction.objects.length, "Duplicate interaction object");
  const keys = /* @__PURE__ */ new Set();
  for (const c of interaction.components) {
    validateComponent(c);
    assert(!keys.has(c.key), "Duplicate interaction component");
    keys.add(c.key);
  }
  assert(bytes(JSON.stringify(interaction)) <= INTERACTION_LIMIT.bytes, "Interaction snapshot size limit exceeded");
}
function denseSheet(workbook) {
  const sheet = Array.isArray(workbook?.sheets) ? workbook.sheets.find((s) => record(s) && s.$type === "spreadsheet" && record(s.cells) && s.cells.$type === "dense") : null;
  if (!sheet) return null;
  const out = { values: sheet.cells.values };
  if (Array.isArray(sheet.cells.numberFormats)) out.numberFormats = sheet.cells.numberFormats;
  return out;
}
function projectComponent(c, canvasWorkbooks) {
  if (!record(c) || c.$type !== "chart" && c.$type !== "table") return null;
  const key = normalizeKey(c.key);
  if (!hex32(key)) return null;
  let sheet = denseSheet(c.workbook);
  if (!sheet && typeof c.workbook?.key === "string") sheet = denseSheet(canvasWorkbooks.find((w) => record(w) && w.key === c.workbook.key));
  if (!sheet) return null;
  const out = { type: c.$type, key, values: sheet.values };
  if (sheet.numberFormats) out.numberFormats = sheet.numberFormats;
  if (typeof c.locale === "string" && localeRe.test(c.locale)) out.locale = c.locale;
  const plot = c.$type === "chart" && Array.isArray(c.plots) ? c.plots[0] : null;
  if (record(plot)) {
    if (typeof plot.$type === "string" && /^[a-z]{1,32}$/.test(plot.$type)) out.plotType = plot.$type;
    if (plot.seriesDirection === "rows" || plot.seriesDirection === "columns") out.seriesDirection = plot.seriesDirection;
    if (plot.primaryOrientation === "x" || plot.primaryOrientation === "y") out.primaryOrientation = plot.primaryOrientation;
    out.defaultSeriesType = SERIES_TYPES.has(plot.defaultSeriesType) ? plot.defaultSeriesType : { numeric: "bubble", radial: "slice", mekko: "mekkoSegment", waterfall: "waterfallSegment" }[plot.$type] ?? "segment";
    if (plot.series?.$type === "explicit" && Array.isArray(plot.series.items)) out.series = plot.series.items.filter((i) => record(i) && index(i.recordIndex)).map((i) => {
      const s = { recordIndex: i.recordIndex };
      if (hex32(i.key)) s.key = i.key;
      if (SERIES_TYPES.has(i.seriesType)) s.seriesType = i.seriesType;
      if (i.color?.$type === "single" && colorRe.test(i.color.color)) s.color = i.color.color;
      if (i.visible === false) s.visible = false;
      return s;
    });
    if (plot.categories?.$type === "explicit" && Array.isArray(plot.categories.items)) out.categories = plot.categories.items.filter((i) => record(i) && index(i.recordIndex)).map((i) => hex32(i.key) ? { recordIndex: i.recordIndex, key: i.key } : { recordIndex: i.recordIndex });
  }
  return out;
}
function buildInteraction(exportJson, dataJson, commit, root) {
  assert(record(exportJson) && Array.isArray(exportJson.objects) && exportJson.projectCommitKey === commit, "Interaction export does not match the pinned commit");
  assert(record(dataJson) && record(dataJson.canvasJson) && dataJson.projectCommitKey === commit, "Interaction data does not match the pinned commit");
  assert(exportJson.objects.length <= INTERACTION_LIMIT.objects, "Interaction object limit exceeded");
  const objects = exportJson.objects.map((o) => {
    assert(record(o) && record(o.interactionManifest), "Renderer did not return an interaction manifest");
    const m = o.interactionManifest;
    assert(m.version === 1 && Array.isArray(m.regions), "Unsupported interaction manifest version");
    assert(m.extendedRegions == null || Array.isArray(m.extendedRegions), "Invalid extended regions");
    const regions = [...m.regions, ...m.extendedRegions ?? []];
    if (regions.every((r) => index(r.paintOrder))) regions.sort((a, b) => a.paintOrder - b.paintOrder);
    const retained = { key: normalizeKey(o.pageObjectKey), type: typeof o.objectType === "string" ? o.objectType.slice(0, 100) : "Object", viewBox: rect(m.coordinateSpace), regions: regions.map(validRegion) };
    if (m.seriesOutlines != null) {
      assert(Array.isArray(m.seriesOutlines), "Invalid series outlines");
      retained.seriesOutlines = m.seriesOutlines.map(validOutline);
    }
    return retained;
  });
  const canvas = dataJson.canvasJson, workbooks = Array.isArray(canvas.workbooks) ? canvas.workbooks : [];
  const components = (Array.isArray(canvas.components) ? canvas.components : []).map((c) => projectComponent(c, workbooks)).filter(Boolean);
  const interaction = { version: 1, source: "data-elements", objects, components };
  validateInteraction(interaction, root);
  return interaction;
}
function tokenize(format) {
  const sections = [[]];
  let i = 0;
  while (i < format.length) {
    const c = format[i];
    if (c === '"') {
      const end = format.indexOf('"', i + 1);
      if (end < 0) return null;
      sections.at(-1).push({ literal: format.slice(i + 1, end) });
      i = end + 1;
      continue;
    }
    if (c === "\\") {
      if (i + 1 >= format.length) return null;
      sections.at(-1).push({ literal: format[i + 1] });
      i += 2;
      continue;
    }
    if (c === "[") {
      const end = format.indexOf("]", i);
      if (end < 0) return null;
      const body = format.slice(i + 1, end);
      if (body.startsWith("$")) sections.at(-1).push({ literal: body.slice(1).split("-")[0] });
      i = end + 1;
      continue;
    }
    if (c === "_") {
      sections.at(-1).push({ literal: " " });
      i += 2;
      continue;
    }
    if (c === "*") {
      i += 2;
      continue;
    }
    if (c === ";") {
      sections.push([]);
      i++;
      continue;
    }
    if (c === "%") {
      sections.at(-1).push({ percent: true, literal: "%" });
      i++;
      continue;
    }
    if ("0#?.,".includes(c)) {
      sections.at(-1).push({ digit: c });
      i++;
      continue;
    }
    if ("$-+/():! ".includes(c)) {
      sections.at(-1).push({ literal: c });
      i++;
      continue;
    }
    if (/[A-Za-z]/.test(c)) return null;
    sections.at(-1).push({ literal: c });
    i++;
  }
  return sections;
}
function compileSection(tokens) {
  const first = tokens.findIndex((t) => t.digit), last = tokens.length - 1 - [...tokens].reverse().findIndex((t) => t.digit);
  if (first < 0) return null;
  const pattern = tokens.slice(first, last + 1);
  if (!pattern.every((t) => t.digit)) return null;
  let text2 = pattern.map((t) => t.digit).join(""), scale = 0;
  while (text2.endsWith(",")) {
    scale++;
    text2 = text2.slice(0, -1);
  }
  const [integer, fraction = ""] = text2.split(".");
  if (fraction.includes(".")) return null;
  return {
    prefix: tokens.slice(0, first).map((t) => t.literal ?? "").join(""),
    suffix: tokens.slice(last + 1).map((t) => t.literal ?? "").join(""),
    percent: tokens.some((t) => t.percent),
    grouping: integer.includes(","),
    minInt: Math.min(21, (integer.match(/0/g) ?? []).length),
    scale: Math.min(scale, 6),
    minFrac: Math.min(20, (fraction.match(/0/g) ?? []).length),
    maxFrac: Math.min(20, fraction.replace(/,/g, "").length)
  };
}
function numberFormatter(locale, options) {
  try {
    return new Intl.NumberFormat(locale ?? void 0, options);
  } catch {
    return new Intl.NumberFormat(void 0, options);
  }
}
function formatCellValue(value, format, locale) {
  if (value === null || value === void 0) return null;
  if (typeof value === "boolean") return value ? "TRUE" : "FALSE";
  if (typeof value === "string") return value;
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  const general = () => numberFormatter(locale, { maximumFractionDigits: 6 }).format(value);
  if (typeof format !== "string" || !format.trim() || /^general$/i.test(format.trim())) return general();
  const sections = tokenize(format);
  if (!sections) return general();
  const compiled = sections.slice(0, 3).map(compileSection);
  let section = compiled[0], magnitude = value;
  if (value === 0 && compiled[2]) section = compiled[2];
  else if (value < 0 && compiled[1]) {
    section = compiled[1];
    magnitude = -value;
  }
  if (!section) return general();
  if (section.percent) magnitude *= 100;
  magnitude /= 1e3 ** section.scale;
  const digits = numberFormatter(locale, { minimumFractionDigits: section.minFrac, maximumFractionDigits: Math.max(section.minFrac, section.maxFrac), useGrouping: section.grouping, minimumIntegerDigits: Math.max(1, section.minInt) }).format(Math.abs(magnitude));
  const sign = magnitude < 0 ? "-" : "";
  return `${sign}${section.prefix}${digits}${section.suffix}`;
}
var componentFor = (interaction, object, region) => interaction.components.find((c) => c.key === (region?.targetObjectKey ?? object.key)) ?? null;
function seriesTypeFor(component, seriesIndex) {
  if (!component || component.type !== "chart") return null;
  return component.series?.find((s) => s.recordIndex === seriesIndex)?.seriesType ?? component.defaultSeriesType ?? "segment";
}
function isPointLike(region, component) {
  if (region.kind === "point") return true;
  return region.kind === "datum" && POINT_TYPES.has(seriesTypeFor(component, region.seriesIndex) ?? "");
}
var cellAt = (c, row, col) => {
  const r = c.values[row];
  return Array.isArray(r) && col < r.length ? r[col] ?? null : void 0;
};
var formatAt = (c, row, col) => {
  const f = c.numberFormats?.[row]?.[col];
  return typeof f === "string" ? f : null;
};
var address = (c, series, category) => c.seriesDirection === "rows" ? [series, category] : c.seriesDirection === "columns" ? [category, series] : null;
var text = (value) => value === void 0 || value === null || value === "" ? null : String(value);
function seriesLabel(c, series) {
  const at = address(c, series, 0);
  return (at && text(cellAt(c, ...at))) ?? `Series ${series}`;
}
function categoryLabel(c, category) {
  const at = address(c, 0, category);
  return (at && text(cellAt(c, ...at))) ?? `Category ${category}`;
}
function valueRow(c, series, category, resolvedValue) {
  const at = address(c, series, category), value = resolvedValue ?? (at ? cellAt(c, ...at) : void 0);
  return { label: seriesLabel(c, series), seriesIndex: series, categoryIndex: category, value: value === void 0 ? null : value, formatted: at ? formatCellValue(value, formatAt(c, ...at), c.locale) : null };
}
function seriesIndexes(object, c) {
  const listed = c?.series?.filter((s) => s.visible !== false).map((s) => s.recordIndex);
  if (listed?.length) return listed;
  return [...new Set(object.regions.filter((r) => r.seriesIndex !== void 0).map((r) => r.seriesIndex))].sort((a, b) => a - b);
}
function categoryIndexes(object, c) {
  if (c?.categories?.length) return c.categories.map((k) => k.recordIndex);
  const seen = [...new Set(object.regions.filter((r) => r.categoryIndex !== void 0).map((r) => r.categoryIndex))].sort((a, b) => a - b);
  if (seen.length) return seen;
  const count = c.seriesDirection === "rows" ? Math.max(0, ...c.values.map((r) => r.length)) : c.values.length;
  return Array.from({ length: Math.max(0, count - 1) }, (_, i) => i + 1);
}
function seriesColor(c, series) {
  return c?.series?.find((s) => s.recordIndex === series)?.color ?? null;
}
function resolveHit(interaction, objectIndex, regionIndex) {
  const object = interaction.objects[objectIndex], region = object.regions[regionIndex], c = componentFor(interaction, object, region);
  const hit = { target: { type: "region", object: objectIndex, region: regionIndex }, kind: region.kind, object: { key: object.key, type: object.type }, region, locale: c?.locale ?? null, title: object.type, subtitle: null, rows: [] };
  if (region.kind === "gantt") {
    hit.title = region.gantt.label || region.gantt.elementType;
    hit.subtitle = region.gantt.elementType === "milestone" ? "Milestone" : "Activity";
    hit.rows = (region.gantt.start === region.gantt.end ? [["Date", region.gantt.start]] : [["Start", region.gantt.start], ["End", region.gantt.end]]).map(([label, value]) => ({ label, value, formatted: value }));
    return hit;
  }
  if (region.kind === "shape") hit.title = region.shape.label;
  if (region.kind === "group") {
    hit.title = region.groupLabel || "Group";
    hit.subtitle = region.groupSize === void 0 ? null : `${region.groupSize} points`;
  }
  if (!c) return hit;
  switch (region.kind) {
    case "group": {
      const target = interaction.objects.find((o) => o.key === (region.targetObjectKey ?? object.key));
      hit.rows = (target?.regions ?? []).filter((r) => r.kind === "point" && r.groupKey === region.groupKey).map((r) => {
        const x = valueRow(c, r.seriesIndex, r.xCategoryIndex), y = valueRow(c, r.seriesIndex, r.yCategoryIndex);
        return { label: seriesLabel(c, r.seriesIndex), value: null, formatted: `${categoryLabel(c, r.xCategoryIndex)}: ${x.formatted ?? "\u2014"} \xB7 ${categoryLabel(c, r.yCategoryIndex)}: ${y.formatted ?? "\u2014"}` };
      });
      break;
    }
    case "shape": {
      if (region.shape.elementType === "football-range") {
        const categoryKey = region.shape.elementKey.split(":")[0], datum = object.regions.find((r) => r.categoryKey === categoryKey && r.categoryIndex !== void 0);
        if (datum) {
          hit.title = categoryLabel(c, datum.categoryIndex);
          hit.subtitle = region.shape.label;
          hit.rows = seriesIndexes(object, c).map((s) => valueRow(c, s, datum.categoryIndex));
        }
      }
      if (c.plotType === "sankey") resolveSankey(hit, c, region.shape, object);
      break;
    }
    case "datum":
      hit.title = categoryLabel(c, region.categoryIndex);
      hit.rows = [valueRow(c, region.seriesIndex, region.categoryIndex, region.resolvedValue)];
      break;
    case "category": {
      hit.title = categoryLabel(c, region.categoryIndex);
      hit.rows = seriesIndexes(object, c).map((s) => valueRow(c, s, region.categoryIndex));
      if (isDumbbellRelationship(region, c)) {
        hit.rows = hit.rows.filter((row) => object.regions.some((r) => r.kind === "datum" && r.categoryIndex === region.categoryIndex && r.seriesIndex === row.seriesIndex));
        hit.subtitle = hit.rows.map((row) => row.label).join(" \u2192 ");
        if (hit.rows.length === 2 && c.seriesDirection) {
          const [a, b] = hit.rows, af = formatAt(c, ...address(c, a.seriesIndex, region.categoryIndex)), bf = formatAt(c, ...address(c, b.seriesIndex, region.categoryIndex));
          if (typeof a.value === "number" && typeof b.value === "number" && af === bf) {
            const delta = b.value - a.value, percent = typeof af === "string" && tokenize(af)?.[0]?.some((t) => t.percent);
            if (Number.isFinite(delta)) hit.rows.push({ label: `Change (${b.label} \u2212 ${a.label})`, value: delta, formatted: (delta > 0 ? "+" : "") + (percent ? `${formatCellValue(delta * 100, null, c.locale)} pp` : formatCellValue(delta, af, c.locale)) });
          }
        }
      }
      break;
    }
    case "series":
      hit.title = seriesLabel(c, region.seriesIndex);
      hit.rows = categoryIndexes(interaction.objects.find((o) => o.key === c.key) ?? object, c).map((k) => ({ ...valueRow(c, region.seriesIndex, k), label: categoryLabel(c, k) }));
      break;
    case "point":
      if (region.seriesIndex === void 0) {
        hit.title = object.type;
        hit.subtitle = "Point";
        break;
      }
      hit.title = seriesLabel(c, region.seriesIndex);
      if (region.xCategoryIndex !== void 0 && region.yCategoryIndex !== void 0)
        hit.rows = [region.xCategoryIndex, region.yCategoryIndex].map((k) => ({ ...valueRow(c, region.seriesIndex, k), label: categoryLabel(c, k) }));
      else hit.subtitle = "Point";
      break;
    case "cell": {
      const value = cellAt(c, region.rowIndex, region.columnIndex);
      hit.title = text(cellAt(c, 0, region.columnIndex)) ?? `Column ${region.columnIndex}`;
      hit.rows = [{ label: text(cellAt(c, region.rowIndex, 0)) ?? `Row ${region.rowIndex}`, value: value === void 0 ? null : value, formatted: formatCellValue(value, formatAt(c, region.rowIndex, region.columnIndex), c.locale) }];
      break;
    }
    default:
      hit.title = object.type;
  }
  return hit;
}
var isDumbbellRelationship = (region, component) => region.kind === "category" && (component?.defaultSeriesType === "dumbbell" || component?.series?.some((s) => s.visible !== false && s.seriesType === "dumbbell"));
function validateInteractionOptions(options) {
  const record2 = (v) => v && typeof v === "object" && !Array.isArray(v);
  if (options === void 0) return;
  if (!record2(options) || Object.keys(options).some((k) => k !== "legend")) throw new Error("Invalid interaction options");
  const l = options.legend;
  if (l === void 0) return;
  if (!record2(l) || Object.keys(l).some((k) => !["mode", "maxRows", "categoryIndexes", "description"].includes(k)) || l.mode !== void 0 && !["auto", "summary", "values"].includes(l.mode) || l.maxRows !== void 0 && (!Number.isInteger(l.maxRows) || l.maxRows < 1 || l.maxRows > 12) || l.categoryIndexes !== void 0 && (!Array.isArray(l.categoryIndexes) || l.categoryIndexes.length > 12 || new Set(l.categoryIndexes).size !== l.categoryIndexes.length || !l.categoryIndexes.every((n) => Number.isInteger(n) && n >= 0)) || l.description !== void 0 && (typeof l.description !== "string" || l.description.length > 240)) throw new Error("Invalid legend disclosure options");
}
function presentHit(hit, options) {
  if (hit.region?.role !== "legend") return hit;
  const l = options?.legend ?? {}, max = l.maxRows ?? 6, total = hit.rows.length;
  const candidates = l.categoryIndexes ? hit.rows.filter((r) => l.categoryIndexes.includes(r.categoryIndex)) : hit.rows;
  const summary = l.mode === "summary" || (l.mode ?? "auto") === "auto" && !l.categoryIndexes && total > max;
  const rows = summary ? [] : candidates.slice(0, max);
  const noun = hit.kind === "group" ? "points" : "observations";
  const count = summary ? `${total} ${noun}` : rows.length < total ? `${rows.length} of ${total} ${noun}` : null;
  return { ...hit, rows, subtitle: [l.description, count, ...summary ? ["Hover a mark for its values."] : []].filter(Boolean).join(" \xB7 ") || hit.subtitle };
}
function resolveSankey(hit, c, shape, object) {
  const node = (key) => {
    const match = /^([A-Za-z0-9+/=]+):(unpinned|-?\d+)$/.exec(key);
    if (!match) return null;
    try {
      return { name: new TextDecoder().decode(Uint8Array.from(atob(match[1]), (c2) => c2.charCodeAt(0))), level: match[2] };
    } catch {
      return null;
    }
  };
  const header = c.values[0] ?? [], levelColumn = header.findIndex((v) => String(v).toLowerCase() === "level");
  if (levelColumn >= 0) return;
  const rows = c.values.slice(1).filter((r) => typeof r[2] === "number" && Number.isFinite(r[2]));
  const row = (label, value) => ({ label, value, formatted: formatCellValue(value, null, c.locale) });
  const flowFor = (key) => {
    const match = /^(.+)>(.+)#(\d+)$/.exec(key);
    if (!match) return null;
    const from = node(match[1]), to = node(match[2]);
    if (!from || !to) return null;
    return rows.filter((r) => r[0] === from.name && r[1] === to.name)[Number(match[3])] ?? null;
  };
  if (shape.elementType === "sankey-link") {
    const flow = flowFor(shape.elementKey);
    if (flow) hit.rows = [row("Flow", flow[2])];
  } else if (shape.elementType === "sankey-node") {
    const n = node(shape.elementKey);
    if (!n) return;
    const rendered = object.regions.filter((r) => r.shape?.elementType === "sankey-link").map((r) => flowFor(r.shape.elementKey)).filter(Boolean);
    const incoming = rendered.filter((r) => r[1] === n.name), outgoing = rendered.filter((r) => r[0] === n.name);
    if (incoming.length) hit.rows.push(row("Incoming", incoming.reduce((n2, r) => n2 + r[2], 0)));
    if (outgoing.length) hit.rows.push(row("Outgoing", outgoing.reduce((n2, r) => n2 + r[2], 0)));
  }
}
function resolveCategory(interaction, objectIndex, categoryIndex) {
  const object = interaction.objects[objectIndex], c = componentFor(interaction, object);
  const hit = { target: { type: "category", object: objectIndex, category: categoryIndex }, kind: "category", object: { key: object.key, type: object.type }, region: null, locale: c?.locale ?? null, title: c ? categoryLabel(c, categoryIndex) : object.type, subtitle: null, rows: [] };
  if (!c) return hit;
  hit.rows = seriesIndexes(object, c).map((s) => {
    const regionIndex = object.regions.findIndex((r) => r.kind === "datum" && r.seriesIndex === s && r.categoryIndex === categoryIndex);
    return { ...valueRow(c, s, categoryIndex, object.regions[regionIndex]?.resolvedValue), regionIndex };
  });
  return hit;
}
function describeHit(hit) {
  return [hit.title, hit.subtitle, ...hit.rows.map((r) => `${r.label}: ${r.formatted ?? "no value"}`)].filter(Boolean).join(". ");
}
function objectModel(interaction, objectIndex) {
  const object = interaction.objects[objectIndex], component = componentFor(interaction, object);
  const pointLike = object.regions.map((r) => isPointLike(r, component));
  const grouped = object.regions.map((r, i) => pointLike[i] && r.kind === "datum" && !r.polygon && r.categoryIndex !== void 0 && component?.primaryOrientation !== "y" && ["line", "area"].includes(seriesTypeFor(component, r.seriesIndex)));
  for (const category of new Set(object.regions.filter((_, i) => grouped[i]).map((r) => r.categoryIndex))) {
    const indexes = object.regions.flatMap((r, i) => grouped[i] && r.categoryIndex === category ? [i] : []), xs = indexes.map((i) => object.regions[i].rect.x + object.regions[i].rect.width / 2);
    if (Math.max(...xs) - Math.min(...xs) > 0.5) for (const i of indexes) grouped[i] = false;
  }
  const categories = [];
  if (grouped.some(Boolean)) {
    const groups = /* @__PURE__ */ new Map();
    object.regions.forEach((r, i) => {
      if (!grouped[i]) return;
      const g = groups.get(r.categoryIndex) ?? { categoryIndex: r.categoryIndex, xs: [], regionIndexes: [] };
      g.xs.push(r.rect.x + r.rect.width / 2);
      g.regionIndexes.push(i);
      groups.set(r.categoryIndex, g);
    });
    const marks = object.regions.filter((_, i) => grouped[i]);
    const yMin = Math.min(...marks.map((r) => r.rect.y)), yMax = Math.max(...marks.map((r) => r.rect.y + r.rect.height));
    const list = [...groups.values()].map((g) => ({ categoryIndex: g.categoryIndex, x: g.xs.reduce((a, b) => a + b, 0) / g.xs.length, regionIndexes: g.regionIndexes, yMin, yMax })).sort((a, b) => a.x - b.x);
    list.forEach((cat, i) => {
      const prev = list[i - 1]?.x, next = list[i + 1]?.x;
      const half = next !== void 0 ? (next - cat.x) / 2 : prev !== void 0 ? (cat.x - prev) / 2 : Math.max(8, object.viewBox.width / 4);
      const left = prev !== void 0 ? (cat.x + prev) / 2 : cat.x - half, right = next !== void 0 ? (cat.x + next) / 2 : cat.x + half;
      cat.band = { x: left, width: Math.max(right - left, 1) };
    });
    categories.push(...list);
  }
  const navigation = [];
  object.regions.forEach((r, i) => {
    if (!grouped[i]) navigation.push({ type: "region", region: i, x: r.rect.x + r.rect.width / 2, y: r.rect.y + r.rect.height / 2 });
  });
  for (const cat of categories) navigation.push({ type: "category", category: cat.categoryIndex, x: cat.x, y: cat.yMin });
  navigation.sort((a, b) => a.x - b.x || a.y - b.y);
  return { object, component, pointLike, grouped, categories, navigation };
}

// src/interaction.mjs
var SVG_NS = "http://www.w3.org/2000/svg";
var mounts = /* @__PURE__ */ new WeakMap();
var THEME_VARIABLES = Object.freeze({
  // The optional shared accent is deliberately unset so default states differ.
  "--grunt-interaction-hover": "var(--grunt-interaction-accent, #D97B2F)",
  "--grunt-interaction-selection": "var(--grunt-interaction-accent, #0A3C47)",
  "--grunt-interaction-surface": "#FFFFFF",
  "--grunt-tooltip-background": "#0F2233",
  "--grunt-tooltip-color": "#FFFFFF",
  "--grunt-tooltip-muted": "#B7C7D4",
  "--grunt-tooltip-border": "#314759"
});
var INTERACTION_STYLE = [
  ".grunt-interactive{position:relative}",
  ".grunt-interaction-layer{position:absolute;overflow:visible;outline:none;user-select:none;-webkit-user-select:none;pointer-events:none;",
  "--grunt-ia-hover:var(--grunt-interaction-hover,var(--grunt-interaction-accent,#D97B2F));--grunt-ia-selection:var(--grunt-interaction-selection,var(--grunt-interaction-accent,#0A3C47));--grunt-ia-surface:var(--grunt-interaction-surface,#FFFFFF)}",
  ".grunt-interaction-layer:focus-visible{outline:2px solid var(--grunt-ia-hover);outline-offset:2px}",
  ".grunt-interaction-object{overflow:visible}",
  ".grunt-hit{fill:#000;fill-opacity:0;stroke:none;pointer-events:none}",
  ".grunt-hit-band{cursor:crosshair}",
  ".grunt-hit-hover{fill:var(--grunt-ia-hover);fill-opacity:.035;stroke:var(--grunt-ia-hover);stroke-width:1.5px;vector-effect:non-scaling-stroke}",
  ".grunt-hit-selected{fill:var(--grunt-ia-selection);fill-opacity:.06;stroke:var(--grunt-ia-selection);stroke-width:2.5px;vector-effect:non-scaling-stroke}",
  ".grunt-series-band{fill:none;stroke:var(--grunt-ia-hover);stroke-width:5px;stroke-opacity:.20;vector-effect:non-scaling-stroke}",
  ".grunt-series-band.grunt-guide-selected{stroke:var(--grunt-ia-selection);stroke-width:7px;stroke-opacity:.30}",
  ".grunt-guide-layer *{pointer-events:none}",
  ".grunt-guide-line{stroke:var(--grunt-ia-hover);stroke-width:1px;stroke-dasharray:4 3;vector-effect:non-scaling-stroke}",
  ".grunt-guide-rect{fill:var(--grunt-ia-hover);fill-opacity:.035;stroke:var(--grunt-ia-hover);stroke-width:1.5px;vector-effect:non-scaling-stroke}",
  ".grunt-guide-point{fill:var(--grunt-ia-surface);stroke:var(--grunt-ia-hover);stroke-width:2px;vector-effect:non-scaling-stroke}",
  ".grunt-guide-selected{stroke:var(--grunt-ia-selection)}",
  ".grunt-guide-line.grunt-guide-selected{stroke-dasharray:none;stroke-width:1.5px}",
  ".grunt-guide-rect.grunt-guide-selected{fill:var(--grunt-ia-selection);fill-opacity:.06;stroke-width:2.5px}",
  ".grunt-guide-point.grunt-guide-selected{stroke-width:3px}",
  ".grunt-tooltip{position:absolute;z-index:20;pointer-events:none;box-sizing:border-box;min-width:min(140px,calc(100vw - 24px));max-width:min(320px,calc(100vw - 24px));max-height:min(420px,calc(100dvh - 24px));overflow:auto;padding:10px 12px;border-radius:7px;",
  'background:var(--grunt-tooltip-background,#0F2233);color:var(--grunt-tooltip-color,#FFFFFF);border:1px solid var(--grunt-tooltip-border,#314759);box-shadow:0 6px 18px rgba(15,34,51,.28);font:12px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}',
  ".grunt-tooltip-pinned{pointer-events:auto;user-select:text;-webkit-user-select:text}",
  ".grunt-tooltip-header{font-weight:600;margin-bottom:4px}",
  ".grunt-tooltip-sub{color:var(--grunt-tooltip-muted,#B7C7D4);font-size:11px;margin-bottom:4px}",
  ".grunt-tooltip-row{display:flex;align-items:center;gap:8px;padding:1px 0}",
  ".grunt-tooltip-swatch{flex:none;width:9px;height:9px;border-radius:2px;background:var(--grunt-interaction-accent,#D97B2F)}",
  ".grunt-tooltip-label{flex:1 1 auto;min-width:0;color:var(--grunt-tooltip-muted,#B7C7D4);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
  ".grunt-tooltip-value{flex:none;font-weight:600;font-variant-numeric:tabular-nums}",
  ".grunt-tooltip-empty{font-weight:400;color:var(--grunt-tooltip-muted,#B7C7D4)}",
  "@media(forced-colors:active){.grunt-hit-hover,.grunt-hit-selected,.grunt-guide-line,.grunt-guide-point,.grunt-series-band{stroke:Highlight;forced-color-adjust:none}.grunt-tooltip{border:1px solid CanvasText;background:Canvas;color:CanvasText}.grunt-tooltip-label,.grunt-tooltip-sub{color:CanvasText}}",
  "@media print{.grunt-interaction-layer,.grunt-tooltip{display:none!important}}"
].join("");
var counter = 0;
function ensureStyle(doc) {
  if (doc.getElementById("grunt-interaction-style")) return;
  const style = doc.createElement("style");
  style.id = "grunt-interaction-style";
  style.textContent = INTERACTION_STYLE;
  doc.head.append(style);
}
function svgEl(doc, name, attrs = {}) {
  const el = doc.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) if (v !== void 0 && v !== null) el.setAttribute(k, String(v));
  return el;
}
function copyAttrs(source, target, names) {
  for (const n of names) {
    const v = source.getAttribute(n);
    if (v !== null) target.setAttribute(n, v);
  }
}
var targetKey = (t) => t ? `${t.type === "region" ? "r" : "c"}:${t.object}:${t.type === "region" ? t.region : t.category}` : null;
var sameTarget = (a, b) => targetKey(a) === targetKey(b);
function mountInteraction({ container, svg, interaction, interactionOptions, label = "Interactive chart", onHoverChange, onSelectionChange }) {
  const doc = container?.ownerDocument, win = doc?.defaultView;
  if (!win || !svg || svg.namespaceURI !== SVG_NS || svg.localName !== "svg" || !container.contains(svg)) throw new Error("mountInteraction needs the rendered <svg> inside its container");
  validateInteraction(interaction, svg);
  validateInteractionOptions(interactionOptions);
  mounts.get(container)?.destroy();
  ensureStyle(doc);
  const id = `grunt-ia-${++counter}`, viewports = objectViewports(svg);
  const models = interaction.objects.map((_, i) => objectModel(interaction, i));
  const overlay = svgEl(doc, "svg", { class: "grunt-interaction-layer", role: "listbox", tabindex: "0", "aria-label": label, "aria-multiselectable": "false", viewBox: svg.getAttribute("viewBox") });
  copyAttrs(svg, overlay, ["preserveAspectRatio"]);
  overlay.id = id;
  overlay.setAttribute("aria-describedby", `${id}-hint`);
  const hint = doc.createElement("span");
  hint.id = `${id}-hint`;
  hint.hidden = true;
  hint.textContent = "Use arrow keys to move between data points, Enter to select, Escape to clear.";
  const options = /* @__PURE__ */ new Map(), regionElements = [], layers = [], inners = [];
  models.forEach((model, o) => {
    const wrapper = svgEl(doc, "g");
    copyAttrs(viewports[o].wrapper, wrapper, ["transform"]);
    const inner = svgEl(doc, "svg", { class: "grunt-interaction-object" });
    copyAttrs(viewports[o].svg, inner, ["viewBox", "width", "height", "x", "y", "preserveAspectRatio"]);
    const hits = svgEl(doc, "g"), guide = svgEl(doc, "g", { class: "grunt-guide-layer" });
    for (const cat of model.categories) {
      const target = { type: "category", object: o, category: cat.categoryIndex };
      const el = svgEl(doc, "rect", { class: "grunt-hit grunt-hit-band", x: cat.band.x, y: cat.yMin - 6, width: cat.band.width, height: cat.yMax - cat.yMin + 12, role: "option", "aria-selected": "false", id: `${id}-o${o}-c${cat.categoryIndex}` });
      el.dataset.gruntHit = targetKey(target);
      el.setAttribute("aria-label", describeHit(resolveCategory(interaction, o, cat.categoryIndex)));
      hits.append(el);
      options.set(targetKey(target), el);
    }
    regionElements.push(model.object.regions.map((r, ri) => {
      const [tag, attributes] = shapeForRegion(r);
      const el = svgEl(doc, tag, { class: "grunt-hit", ...attributes });
      if (r.clipToRect) {
        const clip = svgEl(doc, "clipPath", { id: `${id}-clip-${o}-${ri}` });
        clip.append(svgEl(doc, "rect", r.rect));
        inner.append(clip);
        el.setAttribute("clip-path", `url(#${clip.id})`);
      }
      if (model.grouped[ri]) {
        el.dataset.gruntHit = targetKey({ type: "category", object: o, category: r.categoryIndex });
        el.setAttribute("aria-hidden", "true");
      } else {
        const target = { type: "region", object: o, region: ri };
        el.dataset.gruntHit = targetKey(target);
        el.id = `${id}-o${o}-r${ri}`;
        el.setAttribute("role", "option");
        el.setAttribute("aria-selected", "false");
        el.setAttribute("aria-label", describeHit(presentHit(resolveHit(interaction, o, ri), interactionOptions)));
        options.set(targetKey(target), el);
      }
      hits.append(el);
      return el;
    }));
    inner.append(hits, guide);
    wrapper.append(inner);
    overlay.append(wrapper);
    layers.push(guide);
    inners.push(inner);
  });
  const navigation = models.flatMap((m, o) => m.navigation.map((n) => n.type === "region" ? { type: "region", object: o, region: n.region } : { type: "category", object: o, category: n.category }));
  const tooltip = doc.createElement("div");
  tooltip.className = "grunt-tooltip";
  tooltip.setAttribute("role", "tooltip");
  tooltip.id = `${id}-tip`;
  tooltip.hidden = true;
  container.classList.add("grunt-interactive");
  container.append(overlay, tooltip, hint);
  let hover = null, selected = null, active = null, pointerFocus = false, destroyed = false, pointer = null, down = null;
  const resolve = (t) => presentHit(t.type === "region" ? resolveHit(interaction, t.object, t.region) : resolveCategory(interaction, t.object, t.category), interactionOptions);
  const isText = (event) => !!event.target?.closest?.('text,tspan,textPath,a,button,input,select,textarea,[contenteditable="true"]');
  const selectingText = () => !!win.getSelection()?.toString();
  function parseTarget(event) {
    if (!svg.contains(event.target) || isText(event)) return null;
    for (let o = models.length - 1; o >= 0; o--) {
      const matrix = inners[o].getScreenCTM();
      if (!matrix) continue;
      const p = new win.DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse()), model = models[o];
      const vb = model.object.viewBox;
      if (p.x < vb.x || p.y < vb.y || p.x > vb.x + vb.width || p.y > vb.y + vb.height) continue;
      for (let ri = model.object.regions.length - 1; ri >= 0; ri--) {
        const r = model.object.regions[ri];
        let hit = containsRegion(r, p.x, p.y);
        if (isDumbbellRelationship(r, model.component)) continue;
        if (!hit && model.pointLike[ri] && !r.sector && !r.polygon) {
          const pad = Math.max(0, (10 - Math.min(r.rect.width, r.rect.height)) / 2);
          hit = containsRegion({ rect: { x: r.rect.x - pad, y: r.rect.y - pad, width: r.rect.width + 2 * pad, height: r.rect.height + 2 * pad } }, p.x, p.y);
        }
        if (hit) return model.grouped[ri] ? { type: "category", object: o, category: r.categoryIndex } : { type: "region", object: o, region: ri };
      }
      for (let ri = model.object.regions.length - 1; ri >= 0; ri--) {
        const r = model.object.regions[ri];
        if (!isDumbbellRelationship(r, model.component)) continue;
        const b = r.rect, vertical = b.height >= b.width, pad = 5 / (vertical ? Math.hypot(matrix.a, matrix.b) : Math.hypot(matrix.c, matrix.d));
        const rect2 = vertical ? { ...b, x: b.x - pad, width: b.width + 2 * pad } : { ...b, y: b.y - pad, height: b.height + 2 * pad };
        if (containsRegion({ rect: rect2 }, p.x, p.y)) return { type: "region", object: o, region: ri };
      }
      for (const cat of model.categories) if (p.x >= cat.band.x && p.x <= cat.band.x + cat.band.width && p.y >= cat.yMin - 6 && p.y <= cat.yMax + 6) return { type: "category", object: o, category: cat.categoryIndex };
    }
    return null;
  }
  function rowColor(o, row) {
    if (row.seriesIndex === void 0) return null;
    let color = seriesColor(models[o].component, row.seriesIndex);
    if (color && /^#[0-9a-fA-F]{8}$/.test(color)) color = `#${color.slice(3)}${color.slice(1, 3)}`;
    return color;
  }
  function drawCategory(t, state) {
    const model = models[t.object], layer = layers[t.object], cat = model.categories.find((c) => c.categoryIndex === t.category);
    if (!cat) return;
    layer.append(svgEl(doc, "line", { class: `grunt-guide-line grunt-guide-${state}`, x1: cat.x, x2: cat.x, y1: cat.yMin - 6, y2: cat.yMax + 6 }));
    model.object.regions.forEach((r, i) => {
      if (r.kind !== "datum" || r.categoryIndex !== t.category) return;
      if (model.pointLike[i] && !r.polygon) {
        const point = svgEl(doc, "circle", { class: `grunt-guide-point grunt-guide-${state}`, cx: r.rect.x + r.rect.width / 2, cy: r.rect.y + r.rect.height / 2, r: Math.max(3, Math.min(6, Math.max(r.rect.width, r.rect.height) / 2)) });
        const color = rowColor(t.object, { seriesIndex: r.seriesIndex });
        if (color) point.style.fill = color;
        layer.append(point);
      } else {
        const [tag, attrs] = shapeForRegion(r);
        layer.append(svgEl(doc, tag, { class: `grunt-guide-rect grunt-guide-${state}`, ...attrs }));
      }
    });
  }
  function draw(t, state) {
    const option = options.get(targetKey(t));
    if (state === "selected") option?.setAttribute("aria-selected", "true");
    if (t.type === "category") return drawCategory(t, state);
    const model = models[t.object], r = model.object.regions[t.region];
    if (isDumbbellRelationship(r, model.component)) {
      const b = r.rect, vertical = b.height >= b.width;
      layers[t.object].append(svgEl(doc, "line", { class: `grunt-series-band grunt-guide-${state}`, x1: vertical ? b.x + b.width / 2 : b.x, x2: vertical ? b.x + b.width / 2 : b.x + b.width, y1: vertical ? b.y : b.y + b.height / 2, y2: vertical ? b.y + b.height : b.y + b.height / 2 }));
      for (const mark of model.object.regions) if (mark.kind === "datum" && mark.categoryIndex === r.categoryIndex) {
        const [tag, attrs] = mark.sector || mark.polygon ? shapeForRegion(mark) : ["circle", { cx: mark.rect.x + mark.rect.width / 2, cy: mark.rect.y + mark.rect.height / 2, r: Math.max(mark.rect.width, mark.rect.height) / 2 }];
        const el = svgEl(doc, tag, { class: `grunt-guide-rect grunt-guide-${state}`, ...attrs });
        const ri = model.object.regions.indexOf(mark);
        if (mark.clipToRect) el.setAttribute("clip-path", `url(#${id}-clip-${t.object}-${ri})`);
        layers[t.object].append(el);
      }
      return;
    }
    if (r.kind === "group") {
      const target = models.findIndex((m) => m.object.key === (r.targetObjectKey ?? model.object.key));
      if (target >= 0) {
        for (const mark of models[target].object.regions) if (mark.kind === "point" && mark.groupKey === r.groupKey) {
          const [tag, attrs] = shapeForRegion(mark);
          layers[target].append(svgEl(doc, tag, { class: `grunt-guide-rect grunt-guide-${state}`, ...attrs }));
        }
      }
    }
    if (r.kind === "series") {
      const target = models.findIndex((m) => m.object.key === (r.targetObjectKey ?? model.object.key));
      if (target >= 0) {
        for (const line of models[target].object.seriesOutlines ?? []) if (line.seriesIndex === r.seriesIndex) {
          const [tag, attrs] = shapeForRegion(line);
          layers[target].append(svgEl(doc, tag, { class: `grunt-series-band grunt-guide-${state}`, ...attrs }));
        }
      }
      if (target >= 0 && r.role === "legend") {
        for (const mark of models[target].object.regions) if (mark.seriesIndex === r.seriesIndex && mark.role !== "legend" && ["datum", "point", "series"].includes(mark.kind)) {
          const [tag, attrs] = shapeForRegion(mark);
          layers[target].append(svgEl(doc, tag, { class: `grunt-guide-rect grunt-guide-${state}`, ...attrs }));
        }
      }
    }
    if (model.pointLike[t.region] && !r.sector && !r.polygon) layers[t.object].append(svgEl(doc, "circle", { class: `grunt-guide-point grunt-guide-${state}`, cx: r.rect.x + r.rect.width / 2, cy: r.rect.y + r.rect.height / 2, r: Math.max(3, Math.max(r.rect.width, r.rect.height) / 2) }));
    else option?.classList.add(`grunt-hit-${state}`);
  }
  function paint() {
    for (const el of options.values()) {
      el.classList.remove("grunt-hit-hover", "grunt-hit-selected");
      el.setAttribute("aria-selected", "false");
    }
    for (const layer of layers) layer.replaceChildren();
    if (selected) draw(selected, "selected");
    const shown = hover ?? active;
    if (shown && !sameTarget(shown, selected)) draw(shown, "hover");
  }
  function anchorRect(t) {
    const el = options.get(targetKey(t)) ?? regionElements[t.object][t.region], b = el.getBoundingClientRect();
    if (t.type !== "category") return b;
    const cat = models[t.object].categories.find((c) => c.categoryIndex === t.category);
    const marks = cat.regionIndexes.map((ri) => regionElements[t.object][ri].getBoundingClientRect());
    const top = Math.min(...marks.map((m) => m.top)), bottom = Math.max(...marks.map((m) => m.bottom));
    return { left: b.left + b.width / 2 - 1, width: 2, top, bottom, height: bottom - top };
  }
  function position(t) {
    const anchor = anchorRect(t), c = container.getBoundingClientRect(), w = tooltip.offsetWidth, h = tooltip.offsetHeight, gap = 12;
    let left = hover && pointer ? pointer.x + 16 : anchor.left + anchor.width / 2 - w / 2;
    if (hover && pointer && left + w > win.innerWidth - 8) left = pointer.x - w - 16;
    left = Math.max(8, Math.min(left, win.innerWidth - w - 8));
    let top = hover && pointer ? pointer.y + 16 : anchor.top - h - gap;
    if (hover && pointer && top + h > win.innerHeight - 8) top = pointer.y - h - 16;
    if (top < 8) top = anchor.bottom + gap;
    if (top + h > win.innerHeight - 8) top = Math.max(8, win.innerHeight - h - 8);
    tooltip.style.left = `${left - c.left - container.clientLeft}px`;
    tooltip.style.top = `${top - c.top - container.clientTop}px`;
  }
  function showTooltip() {
    const t = hover ?? active ?? selected;
    if (!t) {
      tooltip.hidden = true;
      tooltip.replaceChildren();
      overlay.setAttribute("aria-describedby", `${id}-hint`);
      return;
    }
    const hit = resolve(t);
    tooltip.replaceChildren();
    tooltip.classList.toggle("grunt-tooltip-pinned", !(hover ?? active) && !!selected);
    const header = doc.createElement("div");
    header.className = "grunt-tooltip-header";
    header.textContent = hit.title;
    tooltip.append(header);
    if (hit.subtitle) {
      const sub = doc.createElement("div");
      sub.className = "grunt-tooltip-sub";
      sub.textContent = hit.subtitle;
      tooltip.append(sub);
    }
    for (const row of hit.rows) {
      const line = doc.createElement("div");
      line.className = "grunt-tooltip-row";
      const swatch = doc.createElement("span");
      swatch.className = "grunt-tooltip-swatch";
      const color = rowColor(t.object, row);
      if (color) {
        swatch.style.backgroundColor = color;
        line.append(swatch);
      }
      const name = doc.createElement("span");
      name.className = "grunt-tooltip-label";
      name.textContent = row.label;
      const value = doc.createElement("span");
      value.className = "grunt-tooltip-value";
      if (row.formatted === null) {
        value.textContent = "\u2014";
        value.classList.add("grunt-tooltip-empty");
        value.setAttribute("aria-label", "No value");
      } else value.textContent = row.formatted;
      line.append(name, value);
      tooltip.append(line);
    }
    tooltip.hidden = false;
    overlay.setAttribute("aria-describedby", `${id}-hint ${id}-tip`);
    position(t);
  }
  const update = () => {
    if (destroyed) return;
    paint();
    showTooltip();
  };
  function setHover(t) {
    if (sameTarget(t, hover)) return;
    hover = t;
    update();
    onHoverChange?.(t ? resolve(t) : null);
  }
  function setActive(t) {
    active = t;
    if (t) overlay.setAttribute("aria-activedescendant", options.get(targetKey(t)).id);
    else overlay.removeAttribute("aria-activedescendant");
    update();
  }
  function setSelection(t) {
    if (sameTarget(t, selected)) return;
    selected = t;
    update();
    onSelectionChange?.(t ? resolve(t) : null);
  }
  const toggle = (t) => setSelection(sameTarget(t, selected) ? null : t);
  function layout() {
    if (destroyed) return;
    const r = svg.getBoundingClientRect(), c = container.getBoundingClientRect();
    overlay.style.left = `${r.left - c.left - container.clientLeft}px`;
    overlay.style.top = `${r.top - c.top - container.clientTop}px`;
    overlay.style.width = `${r.width}px`;
    overlay.style.height = `${r.height}px`;
    if (!tooltip.hidden) position(hover ?? active ?? selected);
  }
  const reposition = () => {
    if (destroyed) return;
    pointer = null;
    setHover(null);
    setActive(null);
    if (!tooltip.hidden && selected) position(selected);
  };
  const onPointerDown = (event) => {
    down = { x: event.clientX, y: event.clientY, type: event.pointerType };
    if (isText(event) || selectingText()) setHover(null);
  };
  const onPointerMove = (event) => {
    if (event.pointerType === "touch" || event.buttons || selectingText()) {
      setHover(null);
      return;
    }
    pointer = { x: event.clientX, y: event.clientY };
    if (active) setActive(null);
    setHover(parseTarget(event));
    if (!tooltip.hidden) position(hover ?? selected);
  };
  const onPointerLeave = () => {
    pointer = null;
    setHover(null);
  };
  const onClick = (event) => {
    if (isText(event) || selectingText() || down && Math.hypot(event.clientX - down.x, event.clientY - down.y) > 5) return;
    if (!svg.contains(event.target)) return;
    const t = parseTarget(event);
    setActive(null);
    if (t) {
      pointerFocus = true;
      if (down?.type !== "touch") overlay.focus({ preventScroll: true });
      pointerFocus = false;
      toggle(t);
    } else setSelection(null);
    if (down?.type === "touch") setHover(null);
    down = null;
  };
  const onFocus = () => {
    if (!pointerFocus && !active && navigation.length) setActive(selected ?? navigation[0]);
  };
  const onBlur = () => {
    pointer = null;
    setHover(null);
    if (active) setActive(null);
  };
  const onKey = (event) => {
    const i = active ? navigation.findIndex((n) => sameTarget(n, active)) : -1;
    const move = (n) => {
      if (!navigation.length) return;
      event.preventDefault();
      setActive(navigation[Math.max(0, Math.min(navigation.length - 1, n))]);
    };
    switch (event.key) {
      case "ArrowRight":
      case "ArrowDown":
        return move(i + 1);
      case "ArrowLeft":
      case "ArrowUp":
        return move(i < 0 ? 0 : i - 1);
      case "Home":
        return move(0);
      case "End":
        return move(navigation.length - 1);
      case "Enter":
      case " ":
        if (active) {
          event.preventDefault();
          toggle(active);
        }
        return;
      case "Escape":
        if (selected || active || hover) {
          event.preventDefault();
          setSelection(null);
          setActive(null);
          setHover(null);
        }
        return;
      default:
    }
  };
  const onOutside = (event) => {
    if (selected && !container.contains(event.target)) setSelection(null);
  };
  const onEscape = (event) => {
    if (event.key === "Escape" && !event.defaultPrevented && event.target !== overlay && (selected || hover)) {
      setSelection(null);
      setHover(null);
    }
  };
  container.addEventListener("pointerdown", onPointerDown);
  container.addEventListener("pointermove", onPointerMove);
  container.addEventListener("pointerleave", onPointerLeave);
  container.addEventListener("pointercancel", onPointerLeave);
  container.addEventListener("click", onClick);
  overlay.addEventListener("keydown", onKey);
  overlay.addEventListener("focus", onFocus);
  overlay.addEventListener("blur", onBlur);
  doc.addEventListener("pointerdown", onOutside, true);
  doc.addEventListener("keydown", onEscape);
  win.addEventListener("resize", layout);
  doc.addEventListener("scroll", reposition, { passive: true, capture: true });
  const observer = typeof win.ResizeObserver === "function" ? new win.ResizeObserver(layout) : null;
  observer?.observe(svg);
  observer?.observe(container);
  layout();
  const handle = {
    overlay,
    tooltip,
    getSelection: () => selected ? resolve(selected) : null,
    getHover: () => hover ? resolve(hover) : null,
    select: (target) => setSelection(target && options.has(targetKey(target)) ? target : null),
    clearSelection: () => setSelection(null),
    destroy() {
      if (destroyed) return;
      destroyed = true;
      observer?.disconnect();
      container.removeEventListener("pointerdown", onPointerDown);
      container.removeEventListener("pointermove", onPointerMove);
      container.removeEventListener("pointerleave", onPointerLeave);
      container.removeEventListener("pointercancel", onPointerLeave);
      container.removeEventListener("click", onClick);
      doc.removeEventListener("pointerdown", onOutside, true);
      doc.removeEventListener("keydown", onEscape);
      win.removeEventListener("resize", layout);
      doc.removeEventListener("scroll", reposition, { capture: true });
      overlay.remove();
      tooltip.remove();
      hint.remove();
      container.classList.remove("grunt-interactive");
      hover = selected = active = null;
      if (mounts.get(container) === handle) mounts.delete(container);
    }
  };
  mounts.set(container, handle);
  return handle;
}
export {
  INTERACTION_STYLE,
  THEME_VARIABLES,
  buildInteraction,
  formatCellValue,
  mountInteraction,
  resolveCategory,
  resolveHit,
  validateInteraction
};
