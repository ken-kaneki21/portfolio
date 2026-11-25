import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import {projects,publicProfile} from './content';
import './styles.css';

const asset = (name: string) => './' + name;

function App() {
  return <>
    <a className="skip" href="#main">Skip to content</a>
    <header className="frame masthead">
      <a className="name" href="#top">{publicProfile.name}</a>
      <nav aria-label="Main navigation">
        <a href="#work">Projects</a>
        <a href="#experience">Experience</a>
        <a href={asset(publicProfile.resume)} download>Resume PDF</a>
      </nav>
    </header>
    <main id="main" className="frame">
      <section id="top" className="hero" aria-labelledby="headline">
        <p className="eyebrow">Data &amp; LLM engineering</p>
        <h1 id="headline">Reliable data.<br/>Evaluated AI.</h1>
        <p className="intro">I build reliable data and AI systems, combining healthcare data engineering with independent work in LLM workflows, retrieval, evaluation and serving.</p>
        <a className="cta" href="#work">Explore the projects <span aria-hidden="true">↘</span></a>
      </section>
      <section id="work" aria-labelledby="work-title">
        <div className="section-head"><h2 id="work-title">Selected projects</h2><a href={asset('evidence/reproduction.txt')}>Reproduce the results</a></div>
        <ul className="project-index">
          {projects.map(p=><li key={p.id}><a href={'#'+p.id}>{p.title}<span aria-hidden="true">↗</span></a></li>)}
        </ul>
        {projects.map(p=><article id={p.id} key={p.id} className="project" aria-labelledby={p.id+'-title'}>
          <div className="project-heading">
            <p className="eyebrow">{p.category}</p>
            <h3 id={p.id+'-title'}>{p.title}</h3>
            <p className="lead">{p.lead}</p>
          </div>
          <dl className="facts">{p.facts.map(f=><div key={f.label}><dt>{f.label}</dt><dd>{f.value}</dd></div>)}</dl>
          <div className="details">{p.sections.map(s=><div key={s.label}><h4>{s.label}</h4><p>{s.text}</p></div>)}</div>
          <div className="links">{p.source && <a href={p.source}>Public source repository</a>}{p.evidence.map(e=><a key={e.path} href={asset(e.path)}>{e.name} <span aria-hidden="true">↗</span></a>)}</div>
        </article>)}
      </section>
      <section id="experience" aria-labelledby="experience-title">
        <div className="section-head"><h2 id="experience-title">Professional experience</h2></div>
        <div className="history"><div><p className="eyebrow">Apr 2026 – present</p><h3>Data Engineer</h3><p>Impilos Analytics (Humbi Analytics)</p></div><p>Healthcare data pipelines in Snowflake and dbt, workflow migration, financial reconciliation and validation of AI-agent answers against reference calculations.</p></div>
        <div className="history"><div><p className="eyebrow">Jul 2024 – Apr 2026</p><h3>Data Analyst · Data Engineering</h3><p>Code Era Technologies</p></div><p>Python and SQL data workflows, cross-database validation and an LLM-assisted document-classification workflow.</p></div>
        <div className="history last"><div><p className="eyebrow">2024</p><h3>B.Tech, Aerospace Engineering</h3><p>IIEST Shibpur</p></div><a href={asset(publicProfile.resume)} download>Download public resume PDF ↗</a></div>
      </section>
    </main>
    <footer className="frame footer"><span>{publicProfile.name} · {publicProfile.location}</span>{publicProfile.contact ? <a href={publicProfile.contact.href}>{publicProfile.contact.label}</a> : <a href="#top">Back to top ↑</a>}</footer>
  </>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><App/></StrictMode>);
