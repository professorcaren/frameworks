const fs = require("fs");
const path = require("path");
const { parse } = require("csv-parse/sync");

const ROOT = path.resolve(__dirname, "../..");
const CSV_PATH = path.join(ROOT, "data/curated_examples.csv");
const SPEECHES_DIR = path.join(ROOT, "data/split_speeches");
const ANNOTATIONS_DIR = path.join(ROOT, "data/speech_annotations");
const OUTPUT_PATH = path.join(__dirname, "../_data/speeches.json");

// Framework name to slug mapping
const FRAMEWORK_SLUGS = {
  "Detective Story": "detective-story",
  Crossroads: "crossroads",
  "Rational Advocate": "rational-advocate",
  "Call to Conscience": "call-to-conscience",
  "Case History": "case-history",
  "Emotional Escalator": "emotional-escalator",
};

function slugify(str) {
  return str
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function cleanText(text) {
  let cleaned = text;

  // Remove <?pagebreak> tags
  cleaned = cleaned.replace(/`?<\?pagebreak[^>]*\?>`?\{=html\}/g, "");

  // Remove {=html} markers
  cleaned = cleaned.replace(/\{=html\}/g, "");

  // Remove {.classname} markers
  cleaned = cleaned.replace(/\{[.#][^}]*\}/g, "");

  // Remove []{#...} anchors
  cleaned = cleaned.replace(/\[\]\{#[^}]*\}/g, "");

  // Remove ::: block markers
  cleaned = cleaned.replace(/^:::.*$/gm, "");

  // Remove [•]{.center} markers and standalone [•]
  cleaned = cleaned.replace(/\[•\]\{\.center\}/g, "");
  cleaned = cleaned.replace(/^\[•\]\s*$/gm, "");

  // Remove <!-- image --> markers
  cleaned = cleaned.replace(/<!--\s*image\s*-->/g, "");

  // Remove standalone [] markers
  cleaned = cleaned.replace(/^\[\]\s*$/gm, "");

  // Remove HTML tags that leaked from markdown source
  cleaned = cleaned.replace(/<\/?p>/g, "");
  cleaned = cleaned.replace(/<br\s*\/?>/g, "\n");
  // Keep <em> and <strong> as-is for rendering
  cleaned = cleaned.replace(/<\/?blockquote>/g, "");
  cleaned = cleaned.replace(/<\/?div[^>]*>/g, "");
  cleaned = cleaned.replace(/<\/?span[^>]*>/g, "");
  cleaned = cleaned.replace(/<\/?h[1-6][^>]*>/g, "");
  cleaned = cleaned.replace(/<\/?ul>/g, "");
  cleaned = cleaned.replace(/<\/?li>/g, "");
  cleaned = cleaned.replace(/<\/?ol>/g, "");
  cleaned = cleaned.replace(/<\/?a[^>]*>/g, "");

  // Normalize tab-separated words (OCR artifact)
  cleaned = cleaned.replace(/([a-zA-Z,;:.'"])\t([a-zA-Z'"])/g, "$1 $2");
  // Also handle tabs after numbers/dates
  cleaned = cleaned.replace(/(\d)\t(\w)/g, "$1 $2");
  // General tab to space
  cleaned = cleaned.replace(/\t/g, " ");

  // Remove ## [Cheers and applause.] style lines
  cleaned = cleaned.replace(/^##\s*\[.*?\]\s*$/gm, "");

  // Remove inline [Cheers and applause.] but keep surrounding text
  cleaned = cleaned.replace(/\s*\[(?:Cheers|Applause|Laughter)[^\]]*\]\s*/gi, " ");

  // Clean up \\- (escaped hyphens from markdown)
  cleaned = cleaned.replace(/\\-/g, "-");
  cleaned = cleaned.replace(/\\!/g, "!");

  // Remove \*\*\*  separator lines
  cleaned = cleaned.replace(/^\\\*\\\*\\\*\s*$/gm, "");
  cleaned = cleaned.replace(/^\*\*\*\s*$/gm, "");

  // Remove inline [] markers (empty bracket artifacts)
  cleaned = cleaned.replace(/\[\]/g, "");

  // Convert markdown emphasis to HTML
  cleaned = cleaned.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  cleaned = cleaned.replace(/\*([^*]+)\*/g, "<em>$1</em>");

  // Clean up multiple blank lines
  cleaned = cleaned.replace(/\n{3,}/g, "\n\n");

  // Trim
  cleaned = cleaned.trim();

  return cleaned;
}

function extractSpeechParts(text) {
  const lines = text.split("\n");
  let title = "";
  let dateLocation = "";
  let contextParagraphs = [];
  let speechBody = [];

  let inBlockquote = false;
  let foundSpeechStart = false;
  let lineIndex = 0;

  // Pass 1: Extract title from first ## heading
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith("## ") || line.startsWith("# ")) {
      title = line.replace(/^#+\s*/, "").replace(/[''`'"]/g, "'").trim();
      lineIndex = i + 1;
      break;
    }
  }

  // Pass 2: Look for date/location (usually the line right after title)
  for (let i = lineIndex; i < Math.min(lineIndex + 5, lines.length); i++) {
    const line = lines[i].trim();
    if (!line) continue;
    // Date/location lines usually contain a year or month/location info
    if (
      /\d{4}/.test(line) &&
      !line.startsWith(">") &&
      !line.startsWith("#") &&
      line.length < 200
    ) {
      dateLocation = line;
      lineIndex = i + 1;
      break;
    }
  }

  // Pass 3: Collect blockquote context and find speech body
  for (let i = lineIndex; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // Skip empty lines between context and speech
    if (!trimmed && !foundSpeechStart) continue;

    // Blockquote lines are editorial context (copyrighted - we'll skip these)
    if (trimmed.startsWith("> ") || trimmed === ">") {
      inBlockquote = true;
      contextParagraphs.push(trimmed.replace(/^>\s?/, ""));
      continue;
    }

    if (inBlockquote && !trimmed) {
      inBlockquote = false;
      continue;
    }

    // Everything else is speech body
    if (!trimmed.startsWith("#")) {
      foundSpeechStart = true;
      speechBody.push(line);
    }
  }

  return {
    title: title || "Untitled",
    dateLocation: dateLocation || "",
    speechBody: speechBody.join("\n").trim(),
  };
}

function main() {
  // Read CSV
  const csvContent = fs.readFileSync(CSV_PATH, "utf-8");
  const records = parse(csvContent, {
    columns: true,
    skip_empty_lines: true,
    trim: true,
  });

  const speeches = [];

  for (const record of records) {
    const speechPath = path.join(SPEECHES_DIR, record.speech_file);

    if (!fs.existsSync(speechPath)) {
      console.error(`Missing speech file: ${speechPath}`);
      continue;
    }

    const rawText = fs.readFileSync(speechPath, "utf-8");
    const cleaned = cleanText(rawText);
    const { title, dateLocation, speechBody } = extractSpeechParts(cleaned);

    // Use title from CSV if available, fallback to extracted
    const displayTitle = record.title || title;
    const speaker = record.speaker || "";
    const frameworkSlug = FRAMEWORK_SLUGS[record.framework] || slugify(record.framework);
    const slug = slugify(`${speaker}-${displayTitle}`);
    const summary = record.brief_summary || "";

    // Convert speech body markdown to simple paragraphs
    // Split on double newlines for paragraphs
    const paragraphs = speechBody
      .split(/\n\n+/)
      .map((p) => p.replace(/\n/g, " ").trim())
      .filter((p) => p.length > 0)
      // Remove empty or near-empty paragraphs
      .filter((p) => p.length > 5)
      // Remove markdown artifacts
      .filter((p) => !p.match(/^\[.*\]\s*$/))
      // Remove footnote-style references
      .filter((p) => !p.match(/^\d+\s*$/));

    // Check for annotations
    let introduction = "";
    let annotatedParagraphs = null;
    const annotationPath = path.join(ANNOTATIONS_DIR, `${slug}.json`);
    if (fs.existsSync(annotationPath)) {
      try {
        const annotation = JSON.parse(
          fs.readFileSync(annotationPath, "utf-8")
        );
        introduction = annotation.introduction || "";
        if (annotation.paragraphs && Array.isArray(annotation.paragraphs)) {
          if (annotation.paragraphs.length === paragraphs.length) {
            annotatedParagraphs = paragraphs.map((text, i) => ({
              text,
              label: annotation.paragraphs[i].label || null,
              comment: annotation.paragraphs[i].comment || null,
            }));
          } else {
            console.warn(`Paragraph count mismatch for ${slug}: annotation has ${annotation.paragraphs.length}, speech has ${paragraphs.length}. Falling back to unlabeled.`);
          }
        }
      } catch (e) {
        console.error(`Error reading annotation for ${slug}:`, e.message);
      }
    }

    // If no valid annotated paragraphs, use unlabeled
    const outputParagraphs = annotatedParagraphs || paragraphs.map((text) => ({
      text,
      label: null,
      comment: null,
    }));

    speeches.push({
      title: displayTitle,
      speaker,
      slug,
      dateLocation,
      framework: record.framework,
      frameworkSlug,
      summary,
      introduction,
      paragraphs: outputParagraphs,
    });
  }

  // Write output
  fs.writeFileSync(OUTPUT_PATH, JSON.stringify(speeches, null, 2));
  console.log(`Generated speeches.json with ${speeches.length} entries`);

  // Summary by framework
  const byFramework = {};
  for (const s of speeches) {
    byFramework[s.framework] = (byFramework[s.framework] || 0) + 1;
  }
  for (const [fw, count] of Object.entries(byFramework)) {
    console.log(`  ${fw}: ${count} speeches`);
  }
}

main();
