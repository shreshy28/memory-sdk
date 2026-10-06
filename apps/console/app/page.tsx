const surfaces = ["API", "Worker", "PostgreSQL / pgvector"];

export default function Home() {
  return (
    <main>
      <p className="eyebrow">Portable memory platform</p>
      <h1>Memory operations,<br />without hidden state.</h1>
      <p className="lede">
        The foundation is online. Later slices add evidence-backed memories, retrieval,
        governance, and lifecycle controls through the same public API.
      </p>
      <section aria-label="Foundation services">
        {surfaces.map((surface, index) => (
          <article key={surface}>
            <span>0{index + 1}</span>
            <h2>{surface}</h2>
            <p>Configured as a replaceable boundary in the local engineering baseline.</p>
          </article>
        ))}
      </section>
    </main>
  );
}
