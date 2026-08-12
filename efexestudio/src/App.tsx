import { useEffect, useState } from 'react'
import {
  ArrowDown,
  ArrowUpRight,
  AudioLines,
  Cable,
  Camera,
  Clock3,
  MapPin,
  Menu,
  MessageCircle,
  Mic2,
  Quote,
  Speaker,
  X,
} from 'lucide-react'
import logo from './assets/efex/logo.png'
import promo from './assets/efex/promo.png'
import studioRoom from './assets/efex/studio-room.webp'

const whatsappUrl =
  'https://wa.me/5562982172516?text=Olá%2C%20EFEX!%20Quero%20consultar%20os%20horários%20disponíveis.'
const instagramUrl = 'https://www.instagram.com/efex_ls/'
const mapsUrl =
  'https://www.google.com/maps/search/?api=1&query=Rua+10%2C+287%2C+Setor+Central%2C+Goiânia%2C+GO'

const services = [
  {
    number: '01',
    title: 'Sala para ensaios',
    text: 'Estrutura pronta para sua banda tocar com presença, conforto e definição.',
    icon: AudioLines,
  },
  {
    number: '02',
    title: 'Gravações',
    text: 'Captação para transformar ideias, demos e sessões em registros de verdade.',
    icon: Mic2,
  },
  {
    number: '03',
    title: 'Sonorização',
    text: 'Som profissional para festas particulares, shows e eventos que pedem impacto.',
    icon: Speaker,
  },
  {
    number: '04',
    title: 'Locação e técnica',
    text: 'Equipamentos e suporte técnico para você focar apenas na performance.',
    icon: Cable,
  },
]

function App() {
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) entry.target.classList.add('is-visible')
        })
      },
      { threshold: 0.12 },
    )

    document.querySelectorAll('[data-reveal]').forEach((element) => observer.observe(element))
    return () => observer.disconnect()
  }, [])

  const closeMenu = () => setMenuOpen(false)

  return (
    <main className="overflow-hidden bg-ink text-white">
      <header className="fixed inset-x-0 top-0 z-50 border-b border-white/10 bg-ink/80 backdrop-blur-xl">
        <div className="mx-auto flex h-18 max-w-[1440px] items-center justify-between px-5 sm:px-8 lg:px-12">
          <a href="#inicio" aria-label="EFEX — início" className="relative z-20">
            <img src={logo} alt="EFEX Estúdio e Sonorização" className="h-12 w-32 object-cover object-center" />
          </a>

          <nav aria-label="Navegação principal" className="hidden items-center gap-8 lg:flex">
            {[
              ['Serviços', '#servicos'],
              ['O estúdio', '#estudio'],
              ['Estrutura', '#estrutura'],
              ['Localização', '#localizacao'],
            ].map(([label, href]) => (
              <a key={href} href={href} className="nav-link">
                {label}
              </a>
            ))}
          </nav>

          <a href={whatsappUrl} target="_blank" rel="noreferrer" className="button-primary header-cta">
            Agendar horário <ArrowUpRight size={17} />
          </a>

          <button
            type="button"
            className="relative z-20 grid size-11 place-items-center border border-white/15 lg:hidden"
            onClick={() => setMenuOpen((open) => !open)}
            aria-expanded={menuOpen}
            aria-label={menuOpen ? 'Fechar menu' : 'Abrir menu'}
          >
            {menuOpen ? <X /> : <Menu />}
          </button>

          <div
            className={`fixed inset-0 z-10 flex min-h-dvh flex-col bg-ink px-6 pb-10 pt-28 transition duration-500 lg:hidden ${
              menuOpen ? 'translate-x-0 opacity-100' : 'pointer-events-none translate-x-full opacity-0'
            }`}
          >
            <nav className="flex flex-col">
              {[
                ['Serviços', '#servicos'],
                ['O estúdio', '#estudio'],
                ['Estrutura', '#estrutura'],
                ['Localização', '#localizacao'],
              ].map(([label, href], index) => (
                <a
                  key={href}
                  href={href}
                  onClick={closeMenu}
                  className="flex items-center justify-between border-b border-white/10 py-5 font-display text-4xl uppercase"
                >
                  {label} <span className="font-mono text-xs text-electric">0{index + 1}</span>
                </a>
              ))}
            </nav>
            <a href={whatsappUrl} target="_blank" rel="noreferrer" className="button-primary mt-auto justify-center">
              Falar no WhatsApp <MessageCircle size={18} />
            </a>
          </div>
        </div>
      </header>

      <section id="inicio" className="hero-section relative min-h-[780px] pt-18 sm:min-h-[850px]">
        <img
          src={studioRoom}
          alt="Sala de ensaio do EFEX Estúdio, equipada com amplificadores, microfones e tratamento acústico"
          className="absolute inset-0 h-full w-full object-cover object-center"
          fetchPriority="high"
        />
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(6,7,9,.97)_0%,rgba(6,7,9,.78)_46%,rgba(6,7,9,.2)_100%)]" />
        <div className="absolute inset-0 bg-[linear-gradient(0deg,#060709_0%,transparent_35%)]" />
        <div className="hero-grid absolute inset-0 opacity-30" />

        <div className="relative mx-auto flex min-h-[calc(100svh-72px)] max-w-[1440px] items-center px-5 py-20 sm:px-8 lg:px-12">
          <div className="max-w-[950px]">
            <div className="hero-kicker mb-7 flex items-center gap-3">
              <span className="h-px w-10 bg-signal" />
              <span>Goiânia · Estúdio & sonorização</span>
            </div>
            <h1 className="hero-title">
              Seu som.
              <span className="block text-stroke">Sem limites.</span>
            </h1>
            <div className="mt-8 grid gap-8 md:grid-cols-[minmax(0,560px)_auto] md:items-end">
              <p className="max-w-xl text-base leading-relaxed text-white/65 sm:text-lg">
                Ensaio, gravação e sonorização com estrutura profissional para sua música ocupar o
                espaço que merece.
              </p>
              <div className="flex flex-wrap gap-3">
                <a href={whatsappUrl} target="_blank" rel="noreferrer" className="button-primary">
                  Reservar a sala <ArrowUpRight size={18} />
                </a>
                <a href="#servicos" className="button-ghost">
                  Conhecer serviços <ArrowDown size={17} />
                </a>
              </div>
            </div>
          </div>
        </div>

        <div className="absolute bottom-0 left-0 right-0 border-y border-white/10 bg-ink/70 backdrop-blur">
          <div className="mx-auto grid max-w-[1440px] grid-cols-2 divide-x divide-white/10 sm:grid-cols-4">
            {[
              ['R$ 80', '2 horas de ensaio'],
              ['6.3K+', 'seguidores'],
              ['04', 'soluções de áudio'],
              ['62', 'Goiânia, GO'],
            ].map(([value, label]) => (
              <div key={label} className="px-4 py-4 sm:px-7 sm:py-5">
                <strong className="font-display text-2xl uppercase sm:text-3xl">{value}</strong>
                <span className="mt-1 block text-[10px] uppercase tracking-[.18em] text-white/45">{label}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="marquee border-b border-white/10 bg-electric py-3 text-ink" aria-hidden="true">
        <div className="marquee-track">
          {Array.from({ length: 2 }).map((_, group) => (
            <div key={group} className="marquee-group">
              <span>Ensaie</span><i>✦</i><span>Grave</span><i>✦</i><span>Toque</span><i>✦</i>
              <span>Amplifique</span><i>✦</i><span>Efex</span><i>✦</i>
            </div>
          ))}
        </div>
      </div>

      <section id="servicos" className="section-shell">
        <div className="section-heading" data-reveal>
          <div>
            <span className="eyebrow">01 / O que fazemos</span>
            <h2>Do primeiro acorde<br />ao som <em>no ar.</em></h2>
          </div>
          <p>
            Tudo o que sua banda, projeto ou evento precisa para soar mais alto, mais limpo e mais
            profissional.
          </p>
        </div>

        <div className="mt-14 border-t border-white/15 sm:mt-20">
          {services.map(({ number, title, text, icon: Icon }) => (
            <article key={number} className="service-row group" data-reveal>
              <span className="font-mono text-xs text-white/35">{number}</span>
              <Icon className="text-electric transition-transform duration-500 group-hover:scale-110" size={28} />
              <h3>{title}</h3>
              <p>{text}</p>
              <ArrowUpRight className="service-arrow" />
            </article>
          ))}
        </div>
      </section>

      <section id="estudio" className="border-y border-white/10 bg-white text-ink">
        <div className="mx-auto grid max-w-[1440px] lg:grid-cols-[1.05fr_.95fr]">
          <div className="relative min-h-[500px] overflow-hidden lg:min-h-[760px]" data-reveal>
            <img
              src={studioRoom}
              alt="Ambiente interno e equipamentos da sala de ensaio EFEX"
              className="absolute inset-0 h-full w-full object-cover transition duration-1000 hover:scale-[1.03]"
              loading="lazy"
            />
            <div className="absolute left-5 top-5 border border-white/30 bg-ink/80 px-4 py-2 font-mono text-[10px] uppercase tracking-[.2em] text-white backdrop-blur">
              Sala EFEX / Goiânia
            </div>
          </div>
          <div className="flex flex-col justify-center px-5 py-16 sm:px-10 lg:px-16 lg:py-24" data-reveal>
            <span className="eyebrow !text-electric-dark">02 / O estúdio</span>
            <h2 className="mt-5 font-display text-[clamp(3.5rem,7vw,7rem)] leading-[.82] uppercase tracking-[-.04em]">
              Sua banda<br />merece <em className="font-serif lowercase text-signal">sentir</em><br />o som.
            </h2>
            <p className="mt-8 max-w-lg text-base leading-relaxed text-ink/65 sm:text-lg">
              Um espaço direto ao ponto: sala tratada, equipamentos prontos e atendimento próximo.
              Você chega com a música. A gente cuida do resto.
            </p>
            <div className="mt-10 grid grid-cols-2 gap-px bg-ink/15">
              {[
                ['Tratamento', 'acústico'],
                ['Backline', 'disponível'],
                ['Acesso', 'fácil'],
                ['Preço', 'justo'],
              ].map(([value, label]) => (
                <div key={value} className="bg-white p-4 sm:p-6">
                  <strong className="font-display text-2xl uppercase">{value}</strong>
                  <span className="block text-xs uppercase tracking-wider text-ink/45">{label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section id="estrutura" className="section-shell">
        <div className="section-heading" data-reveal>
          <div>
            <span className="eyebrow">03 / Por dentro</span>
            <h2>O lugar onde<br />a música <em>acontece.</em></h2>
          </div>
          <a href={instagramUrl} target="_blank" rel="noreferrer" className="button-ghost self-end">
            Ver no Instagram <Camera size={17} />
          </a>
        </div>

        <div className="gallery-grid mt-14 sm:mt-20">
          <figure className="gallery-main" data-reveal>
            <img src={studioRoom} alt="Visão ampla da sala de ensaio EFEX" loading="lazy" />
            <figcaption>Sala principal <span>01</span></figcaption>
          </figure>
          <figure className="gallery-detail" data-reveal>
            <img src={studioRoom} alt="Amplificadores e estrutura técnica no EFEX" loading="lazy" />
            <figcaption>Backline <span>02</span></figcaption>
          </figure>
          <figure className="gallery-promo" data-reveal>
            <img src={promo} alt="Promoção EFEX: duas horas de ensaio por 80 reais" loading="lazy" />
            <figcaption>Hora de marcar <span>03</span></figcaption>
          </figure>
        </div>
      </section>

      <section className="relative overflow-hidden border-y border-white/10 bg-electric px-5 py-20 text-ink sm:px-8 sm:py-28">
        <AudioLines className="absolute -right-16 -top-16 h-80 w-80 opacity-10 sm:h-[500px] sm:w-[500px]" />
        <div className="relative mx-auto max-w-[1100px] text-center" data-reveal>
          <Quote className="mx-auto mb-7" size={35} strokeWidth={1.5} />
          <blockquote className="font-display text-[clamp(3.2rem,9vw,8.5rem)] leading-[.86] uppercase tracking-[-.035em]">
            “Simplesmente<br />o melhor.”
          </blockquote>
          <p className="mt-7 font-mono text-xs uppercase tracking-[.2em]">
            Comentário de cliente no Instagram · @lucianomaiaellite
          </p>
        </div>
      </section>

      <section id="localizacao" className="section-shell !pb-28">
        <div className="grid gap-12 lg:grid-cols-[.8fr_1.2fr] lg:items-end">
          <div data-reveal>
            <span className="eyebrow">04 / Onde estamos</span>
            <h2 className="mt-5 font-display text-[clamp(4rem,8vw,8.5rem)] leading-[.8] uppercase tracking-[-.04em]">
              Chegue.<br /><em>Plugue.</em><br />Toque.
            </h2>
          </div>
          <div className="border border-white/15 bg-white/[.03]" data-reveal>
            <div className="grid gap-8 p-6 sm:p-9 md:grid-cols-2">
              <div>
                <MapPin className="mb-5 text-signal" />
                <span className="meta-label">Endereço</span>
                <address className="mt-2 not-italic leading-relaxed text-white/70">
                  Rua 10, nº 287<br />Setor Central — Goiânia, GO
                </address>
              </div>
              <div>
                <Clock3 className="mb-5 text-electric" />
                <span className="meta-label">Agendamento</span>
                <p className="mt-2 leading-relaxed text-white/70">
                  Consulte os horários disponíveis diretamente pelo WhatsApp.
                </p>
              </div>
            </div>
            <div className="grid border-t border-white/15 sm:grid-cols-2">
              <a href={mapsUrl} target="_blank" rel="noreferrer" className="location-link">
                Abrir no mapa <ArrowUpRight size={18} />
              </a>
              <a href={whatsappUrl} target="_blank" rel="noreferrer" className="location-link sm:border-l">
                Como chegar <MessageCircle size={18} />
              </a>
            </div>
          </div>
        </div>
      </section>

      <section className="cta-section px-5 py-20 sm:px-8 sm:py-28">
        <div className="relative mx-auto max-w-[1200px] text-center" data-reveal>
          <span className="eyebrow justify-center">A sala está pronta</span>
          <h2 className="mt-5 font-display text-[clamp(4rem,11vw,10rem)] leading-[.78] uppercase tracking-[-.05em]">
            Seu próximo<br /><span className="text-electric">ensaio</span> começa<br />aqui.
          </h2>
          <a href={whatsappUrl} target="_blank" rel="noreferrer" className="button-primary mt-10">
            Agendar no WhatsApp <MessageCircle size={19} />
          </a>
        </div>
      </section>

      <footer className="border-t border-white/10 px-5 pb-24 pt-12 sm:px-8 sm:pb-10 lg:px-12">
        <div className="mx-auto grid max-w-[1440px] gap-10 md:grid-cols-[1fr_auto_auto] md:items-end">
          <div>
            <img src={logo} alt="EFEX Estúdio e Sonorização" className="h-20 w-48 object-cover" />
            <p className="mt-3 max-w-sm text-sm leading-relaxed text-white/45">
              Ensaio, gravação e sonorização para quem leva o próprio som a sério.
            </p>
          </div>
          <div className="text-sm text-white/60">
            <span className="meta-label">Contato</span>
            <a href={whatsappUrl} target="_blank" rel="noreferrer" className="mt-2 block hover:text-white">
              (62) 98217-2516
            </a>
            <a href={instagramUrl} target="_blank" rel="noreferrer" className="mt-1 block hover:text-white">
              @efex_ls
            </a>
          </div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-white/30">
            © {new Date().getFullYear()} EFEX<br />Todos os direitos reservados
          </p>
        </div>
      </footer>

      <a
        href={whatsappUrl}
        target="_blank"
        rel="noreferrer"
        className="mobile-whatsapp lg:hidden"
        aria-label="Agendar horário pelo WhatsApp"
      >
        <MessageCircle size={20} /> Agendar horário
      </a>
    </main>
  )
}

export default App
