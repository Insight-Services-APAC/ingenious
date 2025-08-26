// Modern Mermaid.js configuration for MkDocs Material
document.addEventListener('DOMContentLoaded', function() {
  // Initialize Mermaid with configuration
  mermaid.initialize({
    startOnLoad: true,
    theme: 'default',
    themeVariables: {
      primaryColor: '#AE0A46',
      primaryTextColor: '#721357',
      primaryBorderColor: '#D40E8C',
      lineColor: '#3E332D',
      secondaryColor: '#F7F6F5',
      tertiaryColor: '#ffffff'
    },
    flowchart: {
      useMaxWidth: true,
      htmlLabels: true,
      curve: 'basis'
    },
    sequence: {
      useMaxWidth: true,
      wrap: true
    },
    journey: {
      useMaxWidth: true
    },
    gitGraph: {
      useMaxWidth: true
    },
    securityLevel: 'loose'
  });

  // Handle dark mode theme switching
  const observer = new MutationObserver(function(mutations) {
    mutations.forEach(function(mutation) {
      if (mutation.attributeName === 'data-md-color-scheme') {
        const scheme = document.body.getAttribute('data-md-color-scheme');
        const theme = scheme === 'slate' ? 'dark' : 'default';

        mermaid.initialize({
          theme: theme,
          startOnLoad: false
        });

        // Re-render existing diagrams
        mermaid.run({
          querySelector: '.mermaid'
        });
      }
    });
  });

  observer.observe(document.body, {
    attributes: true,
    attributeFilter: ['data-md-color-scheme']
  });
});
