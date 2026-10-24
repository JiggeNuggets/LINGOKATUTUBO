const landingPage = document.querySelector('.landing-page');

if (landingPage && !window.matchMedia('(prefers-reduced-motion: reduce)').matches && 'IntersectionObserver' in window) {
  const revealTargets = landingPage.querySelectorAll([
    '.landing-hero-copy h1',
    '.landing-hero-copy .landing-lead',
    '.landing-hero-copy .landing-context',
    '.landing-hero-actions',
    '.landing-portrait-frame',
    '.landing-discovery-heading .landing-section-title',
    '.landing-discovery-grid .landing-discovery-card',
    '.landing-story-intro .landing-section-title',
    '.landing-story-row',
    '.landing-community-heading .landing-section-title',
    '.landing-apo-feature',
    '.landing-heritage-heading .landing-section-title',
    '.landing-heritage-card',
    '.landing-language-copy .landing-section-title',
    '.landing-quote-card',
    '.landing-cta-inner h2',
    '.landing-cta-inner .landing-button'
  ].join(','));

  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    }
  }, { rootMargin: '0px 0px -4% 0px', threshold: 0.08 });

  revealTargets.forEach((target) => {
    target.setAttribute('data-reveal', '');
    observer.observe(target);
  });
  landingPage.classList.add('landing-motion-ready');
}
