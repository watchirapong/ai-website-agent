import Link from "next/link";

export default function Page() {
  return (
    <div className="relative min-h-screen overflow-hidden bg-slate-950">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_-20%,rgba(120,119,198,0.35),transparent)]" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_80%_60%,rgba(251,191,36,0.08),transparent)]" />
      <header className="relative z-10 border-b border-white/5 bg-slate-950/70 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
          <span className="text-lg font-semibold tracking-tight text-white">build-a-coffee-shop-site-with-menu-and-c</span>
          <nav className="hidden gap-8 text-sm text-slate-400 sm:flex">
            <Link href="#work" className="transition hover:text-white">Work</Link>
            <Link href="#about" className="transition hover:text-white">About</Link>
            <Link href="#contact" className="transition hover:text-white">Contact</Link>
          </nav>
          <Link href="#contact" className="rounded-full px-4 py-2 text-sm font-medium text-white transition bg-[#2563eb] hover:opacity-90">
            Let&apos;s talk
          </Link>
        </div>
      </header>
      <main className="relative z-10">
        <section className="mx-auto max-w-6xl px-6 pb-24 pt-16 sm:pt-24">
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-[#2563eb]">Portfolio</p>
          <h1 className="mt-4 max-w-3xl text-4xl font-bold leading-[1.1] tracking-tight text-white sm:text-5xl md:text-6xl">
            Design and build experiences people remember.
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-slate-400">
            Selected projects, clean typography, and a layout that scales from phone to desktop.
          </p>
          <div className="mt-10 flex flex-wrap gap-4">
            <Link href="#work" className="rounded-full px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-black/20 transition bg-[#2563eb] hover:opacity-90">
              View work
            </Link>
            <Link href="#contact" className="rounded-full border border-white/15 px-6 py-3 text-sm font-medium text-slate-200 transition hover:border-white/30 hover:bg-white/5">
              Contact
            </Link>
          </div>
        </section>
        <section id="work" className="mx-auto max-w-6xl scroll-mt-24 px-6 pb-24">
          <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-500">Featured</h2>
          <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <article
                key={i}
                className="group rounded-2xl border border-white/10 bg-white/[0.03] p-1 transition hover:border-white/20 hover:bg-white/[0.06]"
              >
                <div className="overflow-hidden rounded-xl">
                  <div className="aspect-[4/3] bg-gradient-to-br from-slate-800 to-slate-900 transition group-hover:scale-[1.02]" />
                </div>
                <div className="p-5">
                  <h3 className="font-semibold text-white">Project {i}</h3>
                  <p className="mt-1 text-sm text-slate-500">Brand, UI, and front-end</p>
                </div>
              </article>
            ))}
          </div>
        </section>
        <section id="about" className="border-t border-white/5 bg-slate-900/50 py-20">
          <div className="mx-auto max-w-6xl px-6">
            <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-500">About</h2>
            <p className="mt-4 max-w-2xl text-lg leading-relaxed text-slate-400">
              This is a starter layout generated when the model did not supply a full
              <code className="mx-1 rounded bg-slate-800 px-1.5 py-0.5 text-sm text-slate-300">app/page.tsx</code>
              — replace it with your real content anytime.
            </p>
          </div>
        </section>
        <section id="contact" className="mx-auto max-w-6xl scroll-mt-24 px-6 py-24">
          <div className="rounded-3xl border border-white/10 bg-gradient-to-br from-white/[0.07] to-transparent px-8 py-12 text-center sm:px-16">
            <h2 className="text-2xl font-bold text-white sm:text-3xl">Start a project</h2>
            <p className="mx-auto mt-3 max-w-md text-slate-400">Tell us what you&apos;re building — we&apos;ll take it from here.</p>
            <a href="mailto:hello@example.com" className="mt-8 inline-flex rounded-full px-8 py-3 text-sm font-semibold text-white transition bg-[#2563eb] hover:opacity-90">
              hello@example.com
            </a>
          </div>
        </section>
      </main>
      <footer className="relative z-10 border-t border-white/5 py-8 text-center text-xs text-slate-600">
        build-a-coffee-shop-site-with-menu-and-c · Built with Next.js
      </footer>
    </div>
  );
}
