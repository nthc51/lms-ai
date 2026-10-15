"use client";

import Link from "next/link";
import * as React from "react";
import { SAMPLE_KEYS, SAMPLES, type SampleKey } from "./landing-data";
import "./landing.css";

/** Độ trễ xuất hiện theo thứ tự trong một mục (CSS: transition-delay = --d × 80ms). */
const d = (n: number) => ({ "--d": n }) as React.CSSProperties;
const lineDelay = (n: number) => ({ "--i": n }) as React.CSSProperties;

const QUIZ_TOTAL = 300;
const QUIZ_START = 252;

/** Đồng hồ quiz minh họa: đếm ngược 04:12 rồi quay lại, dừng khi tab ẩn hoặc người dùng giảm chuyển động. */
function useDemoClock() {
  const [left, setLeft] = React.useState(QUIZ_START);
  React.useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = window.setInterval(() => {
      if (!document.hidden) setLeft((v) => (v > 0 ? v - 1 : QUIZ_START));
    }, 1000);
    return () => window.clearInterval(id);
  }, []);
  const text = `${String(Math.floor(left / 60)).padStart(2, "0")}:${String(left % 60).padStart(2, "0")}`;
  return { text, ratio: left / QUIZ_TOTAL };
}

/** Hiện dần từng phần khi cuộn tới (một lần). Không có JS / IntersectionObserver thì mọi thứ hiện sẵn. */
function useReveal(root: React.RefObject<HTMLDivElement | null>) {
  React.useEffect(() => {
    const el = root.current;
    if (!el) return;
    el.classList.add("is-js");
    const targets = el.querySelectorAll("[data-reveal]");
    if (!("IntersectionObserver" in window)) {
      targets.forEach((t) => t.classList.add("is-in"));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries)
          if (e.isIntersecting) {
            e.target.classList.add("is-in");
            io.unobserve(e.target);
          }
      },
      { rootMargin: "0px 0px -10% 0px", threshold: 0.1 },
    );
    targets.forEach((t) => io.observe(t));
    return () => io.disconnect();
  }, [root]);
}

function Timer({ clock }: { clock: { text: string } }) {
  return <span className="timer">{clock.text}</span>;
}

function TimeBar({ ratio }: { ratio: number }) {
  return (
    <div className="timebar">
      <i style={{ transform: `scaleX(${ratio})`, transition: "transform 1s linear" }} />
    </div>
  );
}

const withCites = (p: string) => p.replace(/\[(\d)\]/g, (_, n) => `<a class="cite" href="#lp-ex">${n}</a>`);

/** Phần "Thử hỏi": chọn một câu, xem câu trả lời kèm số trang và đoạn tài liệu được dùng. */
function TrySheet() {
  const [key, setKey] = React.useState<SampleKey>("am");
  const [shown, setShown] = React.useState<SampleKey>("am");
  const [fading, setFading] = React.useState(false);
  const excerpt = React.useRef<HTMLDivElement>(null);
  const s = SAMPLES[shown];

  function choose(k: SampleKey) {
    setKey(k);
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setShown(k);
      return;
    }
    setFading(true);
    window.setTimeout(() => {
      setShown(k);
      setFading(false);
    }, 200);
  }

  function onSheetClick(e: React.MouseEvent) {
    const target = (e.target as HTMLElement).closest(".cite, .source a");
    if (!target || !excerpt.current) return;
    e.preventDefault();
    excerpt.current.scrollIntoView({ block: "nearest", behavior: "smooth" });
    excerpt.current.animate([{ transform: "translateY(8px)", opacity: 0.4 }, { transform: "none", opacity: 1 }], {
      duration: 400,
      easing: "cubic-bezier(.16,1,.3,1)",
    });
  }

  return (
    <section className="try" id="thu" aria-labelledby="h-try">
      <div className="try-index">
        <h2 className="sr-only" id="h-try">
          Thử hỏi AI Tutor
        </h2>
        <div className="try-names" role="group" aria-label="Chọn một câu hỏi">
          {SAMPLE_KEYS.map((k) => (
            <button key={k} type="button" aria-pressed={key === k} onClick={() => choose(k)}>
              {SAMPLES[k].label}
            </button>
          ))}
        </div>
        <div className="try-note" data-reveal>
          <p>Bốn câu hỏi về bài Kỹ thuật truyền thông. Bấm số trong ô vàng để xem đoạn tài liệu được dùng.</p>
          <p>Câu cuối nằm ngoài tài liệu, nên AI nói thẳng là không có.</p>
        </div>
      </div>
      <div className="stage">
        {/* onClick chỉ bắt click của các liên kết [n] / "Mở PDF" bên trong (bàn phím: Enter trên liên kết cũng là click) */}
        <article className={fading ? "sheet fading" : "sheet"} data-ui aria-live="polite" onClick={onSheetClick}>
          <div className="sheet-head">
            <span>AI Tutor · Kỹ thuật truyền thông</span>
            <span>Phạm vi: cả khóa</span>
          </div>
          <div className="q-bubble">{s.question}</div>
          <div className="answer">
            {s.refusal ? (
              <p className="refuse">{s.refusal}</p>
            ) : (
              s.paragraphs?.map((p) => <p key={p} dangerouslySetInnerHTML={{ __html: withCites(p) }} />)
            )}
          </div>
          {s.sources ? (
            <div className="sources">
              {s.sources.map((src, i) => (
                <div className="source" key={src.page}>
                  <span className="cite">{i + 1}</span>
                  <span>{src.title}</span>
                  <a href="#lp-ex">Mở PDF trang {src.page}</a>
                </div>
              ))}
            </div>
          ) : null}
          {s.excerpt ? (
            <div className="excerpt" id="lp-ex" ref={excerpt}>
              <div className="ex-top">
                <span>Đoạn được dùng</span>
                <span>trang {s.excerpt.page}</span>
              </div>
              <p dangerouslySetInnerHTML={{ __html: s.excerpt.html }} />
            </div>
          ) : null}
          <div className="followups">
            {s.followups.map((f) => (
              <span key={f}>{f}</span>
            ))}
          </div>
        </article>
      </div>
    </section>
  );
}

/** Trang chủ cho khách: giới thiệu AI Tutor trả lời theo tài liệu và ghi số trang. */
export function Landing() {
  const root = React.useRef<HTMLDivElement>(null);
  const clock = useDemoClock();
  useReveal(root);

  return (
    <div className="landing" ref={root}>
      <header className="mast">
        <div className="bar">
          <Link className="wordmark" href="/" aria-label="LMS-AI, trang chủ">
            LMS-AI
          </Link>
          <nav className="tab" aria-label="Trang chủ">
            <a href="#thu">Thử hỏi</a>
            <a href="#cach">Cách hoạt động</a>
            <a href="#giang-vien">Cho giảng viên</a>
          </nav>
          <div className="bar-end">
            <Link className="link hide-s" href="/login">
              Đăng nhập
            </Link>
            <Link className="link" href="/register">
              Tạo tài khoản
            </Link>
          </div>
        </div>

        <div className="mosaic" aria-hidden="true">
          <div className="cell c-a">
            <div className="ui-slide" data-ui>
              <div className="s-top">
                <span>Kỹ thuật truyền thông · Chương 3</span>
                <span>trang 49</span>
              </div>
              <h4>Phổ của tín hiệu AM</h4>
              <ul>
                <li>Gồm sóng mang và hai dải biên đối xứng</li>
                <li>
                  <span className="hl sweep" data-reveal>
                    Băng thông B = 2·f<sub>max</sub>
                  </span>{" "}
                  của tín hiệu tin tức
                </li>
                <li>Hiệu suất công suất thấp khi chỉ số điều chế nhỏ</li>
              </ul>
            </div>
          </div>
          <div className="cell c-b">
            <span className="big-num">trang 49</span>
            <span className="tile-note">là nơi câu trả lời lấy ra</span>
          </div>
          <div className="cell c-c">
            <div className="ui-chat" data-ui>
              <div className="q-bubble">Băng thông của AM bằng bao nhiêu?</div>
              <div className="a-text">
                Bằng hai lần tần số cao nhất của tín hiệu tin tức <span className="cite">2</span>
              </div>
              <div className="src-line">
                <span className="cite">2</span>
                <span>Chương 3 · trang 49 · Mở PDF</span>
              </div>
            </div>
          </div>
          <div className="cell c-d">
            <span className="big-num">174</span>
            <span className="tile-note">trang slide đọc xong trong khoảng 90 giây</span>
          </div>
          <div className="cell c-e">
            <span className="tile-note tile-formula">
              N<sub>0</sub>/2
            </span>
          </div>
          <div className="cell c-f">
            <span className="tile-note">Sáng, tối hoặc giấy</span>
          </div>
          <div className="cell c-h">
            <div className="ui-quiz" data-ui>
              <div className="quiz-top">
                <span>Câu 3/10</span>
                <Timer clock={clock} />
              </div>
              <TimeBar ratio={clock.ratio} />
              <div>Tín hiệu AM có băng thông bằng?</div>
              <div className="opt">
                <b>A</b>
                <span>
                  f<sub>max</sub>
                </span>
              </div>
              <div className="opt on">
                <b>B</b>
                <span>
                  2·f<sub>max</sub>
                </span>
              </div>
              <div className="opt">
                <b>C</b>
                <span>
                  4·f<sub>max</sub>
                </span>
              </div>
            </div>
          </div>
          <div className="cell c-i">
            <span className="tile-note">Giảng viên duyệt từng câu hỏi</span>
          </div>
        </div>
      </header>

      <main id="main">
        <section className="hero" aria-labelledby="h-hero">
          <div className="hero-left after-lines">
            <p className="standfirst">
              AI Tutor chỉ trả lời từ tài liệu giảng viên tải lên, và ghi rõ trang để bạn mở ra kiểm.
            </p>
            <div className="actions">
              <a className="btn" href="#thu">
                Thử hỏi một câu
              </a>
              <a className="link" href="#cach">
                Xem cách hoạt động
              </a>
            </div>
          </div>
          <h1 className="lines" id="h-hero">
            <span className="line">
              <span data-line style={lineDelay(0)}>
                Hỏi bài,
              </span>
            </span>
            <span className="line">
              <span data-line style={lineDelay(1)}>
                có số trang.
              </span>
            </span>
          </h1>
        </section>

        <TrySheet />

        <section className="how" id="cach" aria-labelledby="h-how">
          <h2 id="h-how" data-reveal>
            Tải lên một lần, hỏi cả kỳ
          </h2>
          <div className="stages" data-ui>
            <div className="stage-seg seg-1" data-reveal style={d(1)}>
              Vài giây<small>Trước tiên, giảng viên tải PDF bài giảng lên bài học.</small>
            </div>
            <div className="stage-seg seg-2" data-reveal style={d(2)}>
              Khoảng 90 giây<small>Sau đó hệ thống đọc từng trang, kể cả trang ảnh và công thức.</small>
            </div>
            <div className="stage-seg seg-3" data-reveal style={d(3)}>
              Cả học kỳ<small>Rồi học viên hỏi, làm quiz và ôn thẻ trên đúng tài liệu ấy.</small>
            </div>
          </div>
          <div className="stage-notes">
            <p className="n1" data-reveal style={d(1)}>
              Trước tiên, giảng viên tải PDF bài giảng lên bài học.
            </p>
            <p className="n2" data-reveal style={d(2)}>
              Sau đó hệ thống đọc từng trang, kể cả trang ảnh và công thức, rồi chia thành đoạn để tìm.
            </p>
            <p className="n3" data-reveal style={d(3)}>
              Rồi học viên hỏi, làm quiz và ôn thẻ trên đúng tài liệu ấy. Tìm được cả khi gõ không dấu.
            </p>
          </div>
        </section>

        <section className="feat" aria-labelledby="h-feat">
          <div className="feat-intro">
            <h2 id="h-feat" data-reveal>
              Ôn ngay trong bài học
            </h2>
          </div>

          <div className="row">
            <p className="side" data-reveal>
              Giảng viên đặt từ 1 đến 240 phút<span>Hết giờ bài tự nộp, kể cả khi đã đóng tab</span>
            </p>
            <div>
              <h3 data-reveal>Quiz có đồng hồ</h3>
              <p data-reveal style={d(1)}>
                Mỗi người nhận câu hỏi theo một thứ tự riêng, tải lại trang vẫn giữ nguyên. Đồng hồ chạy theo giờ
                máy chủ, nên không ai “dừng giờ” được.
              </p>
            </div>
            <figure data-reveal style={d(2)}>
              <div className="frag f1" data-ui>
                <div className="fpad">
                  <div className="quiz-top">
                    <span>Kiểm tra chương 3</span>
                    <Timer clock={clock} />
                  </div>
                  <TimeBar ratio={clock.ratio} />
                  <div className="frag-q">Câu 3/10 · Tín hiệu AM có băng thông bằng?</div>
                  <div className="opt">
                    <b>A</b>
                    <span>
                      f<sub>max</sub>
                    </span>
                  </div>
                  <div className="opt on">
                    <b>B</b>
                    <span>
                      2·f<sub>max</sub>
                    </span>
                  </div>
                  <div className="opt">
                    <b>C</b>
                    <span>
                      4·f<sub>max</sub>
                    </span>
                  </div>
                  <div className="opt">
                    <b>D</b>
                    <span>Bằng tần số sóng mang</span>
                  </div>
                  <div className="frag-foot">
                    <span>Đã lưu tự động</span>
                    <span>Câu tiếp</span>
                  </div>
                </div>
              </div>
              <figcaption className="sr-only">Màn hình làm quiz có đồng hồ đếm ngược</figcaption>
            </figure>
          </div>

          <div className="row">
            <p className="side" data-reveal>
              Dựa trên đoạn tài liệu đã sinh ra câu hỏi<span>Giải thích một lần, lần sau mở lại ngay</span>
            </p>
            <div>
              <h3 data-reveal>Giải thích câu sai</h3>
              <p data-reveal style={d(1)}>
                Nộp bài xong, bấm vào câu làm sai hoặc bỏ trống. AI nói vì sao đáp án kia đúng, kèm trang tài liệu
                để đọc lại.
              </p>
            </div>
            <figure className="r2" data-reveal style={d(2)}>
              <div className="frag f2" data-ui>
                <div className="fpad">
                  <div className="quiz-top">
                    <span>Kết quả · 7/10</span>
                    <span className="frag-meta">Nộp lúc 09:41</span>
                  </div>
                  <div className="res-row">
                    <span>Câu 2 · Hiệu suất AM</span>
                    <em>Đúng</em>
                  </div>
                  <div className="res-row bad">
                    <span>Câu 3 · Băng thông AM</span>
                    <em>Sai</em>
                  </div>
                  <div className="ai-explain">
                    <b>AI giải thích</b>Phổ AM có hai dải biên đối xứng quanh f<sub>c</sub>, mỗi dải rộng f
                    <sub>max</sub>, nên băng thông là 2·f<sub>max</sub> chứ không phải f<sub>max</sub>.{" "}
                    <span className="cite">tr. 49</span>
                  </div>
                </div>
              </div>
              <figcaption className="sr-only">Trang kết quả quiz có phần AI giải thích</figcaption>
            </figure>
          </div>

          <div className="row">
            <p className="side" data-reveal>
              Phím cách để lật, N là chưa nhớ, C là đã nhớ<span>Soạn một lần, dùng chung cả lớp</span>
            </p>
            <div>
              <h3 data-reveal>Thẻ ôn và đề cương</h3>
              <p data-reveal style={d(1)}>
                Studio soạn đề cương, bản tóm tắt và bộ thẻ ghi nhớ từ tài liệu của bài. Mỗi ý đều có số trang, bấm
                vào là mở đúng chỗ.
              </p>
            </div>
            <figure data-reveal style={d(2)}>
              <div className="frag f3" data-ui>
                <div className="fpad">
                  <div className="quiz-top">
                    <span>Thẻ 4/18</span>
                    <span className="frag-meta">Đã nhớ 3</span>
                  </div>
                  <div className="fc-card">Mật độ phổ công suất của nhiễu trắng?</div>
                  <div className="fc-keys">
                    <span>
                      <kbd>Space</kbd> lật
                    </span>
                    <span>
                      <kbd>N</kbd> chưa nhớ
                    </span>
                    <span>
                      <kbd>C</kbd> đã nhớ
                    </span>
                  </div>
                </div>
              </div>
              <figcaption className="sr-only">Một thẻ ghi nhớ trong Studio</figcaption>
            </figure>
          </div>

          <div className="row">
            <p className="side" data-reveal>
              Chọn từ hai ghi chú trở lên<span>Ghi chú lưu theo từng bài, xem lại ở trang Ghi chú</span>
            </p>
            <div>
              <h3 data-reveal>Gộp ghi chú</h3>
              <p data-reveal style={d(1)}>
                Lưu câu trả lời hay vào ghi chú ngay trong cuộc hỏi đáp. Trước kỳ thi, chọn vài ghi chú và để AI gộp
                lại thành một đề cương ôn tập.
              </p>
            </div>
            <figure className="r2" data-reveal style={d(2)}>
              <div className="frag f4" data-ui>
                <div className="fpad">
                  <div className="quiz-top">
                    <span>Ghi chú của tôi</span>
                    <span className="frag-meta">Đã chọn 2</span>
                  </div>
                  <div className="note-item">
                    <i />
                    <span>
                      Băng thông AM = 2·f<sub>max</sub>, trang 49
                    </span>
                  </div>
                  <div className="note-item">
                    <i />
                    <span>
                      Shannon: C = B·log<sub>2</sub>(1 + S/N), trang 31
                    </span>
                  </div>
                  <div className="note-item off">
                    <i />
                    <span>AWGN là mô hình của nhiễu nhiệt, trang 24</span>
                  </div>
                  <span className="mini-btn">Tạo đề cương từ 2 ghi chú</span>
                </div>
              </div>
              <figcaption className="sr-only">Trang ghi chú, chọn hai ghi chú để tạo đề cương</figcaption>
            </figure>
          </div>
        </section>

        <section className="teach" id="giang-vien" aria-labelledby="h-teach">
          <h2 id="h-teach" data-reveal>
            Giảng viên duyệt trước
          </h2>
          <p className="lead" data-reveal style={d(1)}>
            Câu hỏi do AI soạn chỉ đến tay học viên sau khi giảng viên đọc, sửa hoặc loại bỏ. Bản đề cương đã sửa
            mang nhãn “Giảng viên đã duyệt” và không bị ghi đè khi tài liệu thay đổi.
          </p>
          <div className="teach-grid">
            <figure className="t-photo" data-reveal>
              <div className="review" data-ui>
                <div className="rv-head">
                  <span>Câu hỏi chờ duyệt · Chương 3</span>
                  <span className="badge-ok">8 câu</span>
                </div>
                <div className="rv-q">
                  <p>Khi chỉ số điều chế bằng 1, công suất hai dải biên chiếm bao nhiêu phần tổng công suất AM?</p>
                  <ol className="rv-opts">
                    <li>A. 1/2</li>
                    <li className="ok">B. 1/3</li>
                    <li>C. 2/3</li>
                    <li>D. 1/4</li>
                  </ol>
                </div>
                <div className="rv-src">Lấy từ trang 50 · Độ khó: trung bình</div>
                <div className="rv-actions">
                  <span>Duyệt</span>
                  <span>Sửa</span>
                  <span>Loại</span>
                </div>
                <div className="rv-q rv-done">
                  <p>
                    Đề cương chương 3 · Điều chế biên độ <span className="badge-ok">Giảng viên đã duyệt</span>
                  </p>
                  <span className="frag-meta">Sửa lúc 14:20 · 6 mục · mỗi mục có số trang</span>
                </div>
              </div>
              <p className="t-over">
                Mỗi câu ghi trang mà AI đã dựa vào. Câu nào AI tự kiểm thấy nghi sai được gắn cờ để giảng viên xem kỹ.
              </p>
            </figure>
            <div className="t-side" data-reveal style={d(2)}>
              <div className="t-tile" aria-hidden="true">
                <svg viewBox="0 0 120 160">
                  <path d="M0 0h86l34 34v126H0z" fill="#fff" />
                  <path d="M86 0v34h34z" fill="#16181b" />
                  <g fill="#16181b" opacity=".18">
                    <rect x="14" y="22" width="56" height="7" />
                    <rect x="14" y="44" width="90" height="5" />
                    <rect x="14" y="56" width="84" height="5" />
                    <rect x="14" y="68" width="90" height="5" />
                    <rect x="14" y="104" width="78" height="5" />
                    <rect x="14" y="116" width="90" height="5" />
                    <rect x="14" y="128" width="60" height="5" />
                  </g>
                  <rect x="12" y="84" width="92" height="9" fill="#ffe68f" />
                  <circle cx="106" cy="88.5" r="6" fill="#16181b" />
                </svg>
              </div>
              <dl className="facts">
                <div>
                  <dt>Trang đọc được</dt>
                  <dd>174 trong khoảng 90 giây</dd>
                </div>
                <div>
                  <dt>Đoạn tìm cho mỗi câu hỏi</dt>
                  <dd>6 đoạn</dd>
                </div>
                <div>
                  <dt>Lượt tạo trong Studio</dt>
                  <dd>10 mỗi giờ</dd>
                </div>
                <div>
                  <dt>Chế độ đọc</dt>
                  <dd>Sáng, tối, giấy</dd>
                </div>
              </dl>
            </div>
          </div>
        </section>

        <section className="close" aria-labelledby="h-close">
          <h2 id="h-close" data-reveal>
            Câu nào cũng
            <br />
            có trang.
          </h2>
          <div className="close-foot">
            <p data-reveal style={d(1)}>
              Tạo tài khoản học viên, vào khóa học và hỏi ngay bên cạnh bài giảng.
            </p>
            <Link className="btn" href="/register" data-reveal style={d(2)}>
              Tạo tài khoản
            </Link>
          </div>
        </section>
      </main>

      <footer className="foot">
        <div className="foot-top">
          <div className="foot-notes">
            <p>
              <b>LMS-AI</b>Đồ án tốt nghiệp, nền tảng học trực tuyến có AI Tutor.
            </p>
            <p>Khóa học, bài giảng PDF và video, quiz, Studio, ghi chú, trang quản trị.</p>
          </div>
          <a className="link" href="#main">
            Về đầu trang
          </a>
        </div>
        <Link className="contact" href="/explore">
          <span>Khám phá</span>
          <span>khóa học</span>
        </Link>
        <div className="meta">
          <nav aria-label="Liên kết cuối trang">
            <Link className="link" href="/login">
              Đăng nhập
            </Link>
            <Link className="link" href="/register">
              Đăng ký
            </Link>
          </nav>
          <p>Chữ: Be Vietnam Pro</p>
          <p>Việt Nam, 2026</p>
        </div>
      </footer>
    </div>
  );
}
