const markdownIt = require("markdown-it");

module.exports = function (eleventyConfig) {
  // Passthrough copy
  eleventyConfig.addPassthroughCopy("css");
  eleventyConfig.addPassthroughCopy({ "pages/robots.txt": "robots.txt" });

  // Markdown library
  const md = markdownIt({ html: true, breaks: false, linkify: true });
  eleventyConfig.setLibrary("md", md);

  // Filter: render markdown string to HTML
  eleventyConfig.addFilter("markdown", function (content) {
    if (!content) return "";
    return md.render(content);
  });

  // Filter: slugify
  eleventyConfig.addFilter("slugify", function (str) {
    if (!str) return "";
    return str
      .toLowerCase()
      .replace(/[^\w\s-]/g, "")
      .replace(/\s+/g, "-")
      .replace(/-+/g, "-")
      .trim();
  });

  // Filter: find framework by slug
  eleventyConfig.addFilter("findFramework", function (frameworks, slug) {
    return frameworks.find((f) => f.slug === slug);
  });

  // Filter: speeches for a given framework slug
  eleventyConfig.addFilter("speechesForFramework", function (speeches, frameworkSlug) {
    return speeches.filter((s) => s.frameworkSlug === frameworkSlug);
  });

  // Collection: speeches grouped by framework
  eleventyConfig.addCollection("speechesByFramework", function (collectionApi) {
    const speeches = require("./_data/speeches.json");
    const grouped = {};
    for (const speech of speeches) {
      if (!grouped[speech.frameworkSlug]) {
        grouped[speech.frameworkSlug] = [];
      }
      grouped[speech.frameworkSlug].push(speech);
    }
    return grouped;
  });

  return {
    dir: {
      input: "pages",
      includes: "../_includes",
      data: "../_data",
      output: "_site",
    },
    pathPrefix: "/frameworks/",
    templateFormats: ["njk", "md"],
    htmlTemplateEngine: "njk",
    markdownTemplateEngine: "njk",
  };
};
