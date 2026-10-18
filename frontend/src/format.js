// "Matrix, The (1999)" -> { name: "The Matrix", year: "1999" }
export function formatTitle(raw) {
  const m = raw.match(/^(.*) \((\d{4})\)$/);
  let name = (m ? m[1] : raw).split(" (")[0]; // drop alternate titles in brackets
  const article = name.match(/^(.*), (The|A|An)$/);
  if (article) name = `${article[2]} ${article[1]}`;
  return { name, year: m ? m[2] : "" };
}
