import React, { useEffect } from 'react';
import Navbar from './components/Navbar';
import Hero from './components/Hero';
import About from './components/About';
import Work from './components/Work';
import Trusted from './components/Trusted';
import Growth from './components/Growth';
import Plan from './components/Plan';
import Number from './components/Number';
import Feedback from './components/Feedback';
import Blog from './components/Blog';
import CTA from './components/CTA';
import Footer from './components/Footer';

function App() {
  useEffect(() => {
    // Re-initialize Webflow
    if (window.Webflow && typeof window.Webflow.ready === 'function') {
      window.Webflow.ready();
    }
  }, []);

  return (
    <div className="pages-wrapper">
      <Navbar />
      <Hero />
      <About />
      <Work />
      <Trusted />
      <Growth />
      <Plan />
      <Number />
      <Feedback />
      <Blog />
      <CTA />
      <Footer />
    </div>
  );
}

export default App;
