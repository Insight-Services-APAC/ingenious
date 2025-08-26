// Modern Mermaid.js configuration for MkDocs Material
document.addEventListener('DOMContentLoaded', function() {
  // Initialize Mermaid with configuration
  mermaid.initialize({
    startOnLoad: true,
    theme: 'default',
    themeVariables: {
      primaryColor: '#2196F3',
      primaryTextColor: '#1976D2',
      primaryBorderColor: '#42A5F5',
      lineColor: '#757575',
      secondaryColor: '#f5f5f5',
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
