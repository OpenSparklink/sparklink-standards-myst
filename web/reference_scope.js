// Resolve explicit standard citations without linking into the wrong document.
(() => {
  function scopeFor(documents,current,before){
    const sentence=before.slice(Math.max(before.lastIndexOf('。'),before.lastIndexOf('；'),before.lastIndexOf(';'))+1);
    const mentions=[...sentence.matchAll(/GB\s*\/?\s*T\s*(\d+)(?:\s*[.．]\s*(\d+))?(?:\s*[-—－]\s*(\d{4}))?/g)];
    const latest=mentions.at(-1),self=Math.max(sentence.lastIndexOf('本文件'),sentence.lastIndexOf('本标准'));
    if(latest&&self<=latest.index){
      const prefix='GBT-'+latest[1]+(latest[2]?'.'+latest[2]:'')+'-';
      return documents.find(d=>d.code.startsWith(prefix)&&(!latest[3]||d.code===prefix+latest[3]))||null;
    }
    if(/(?:ISO|IEC|IEEE|3GPP|ITU)[ /-]/.test(sentence)&&self<0)return null;
    return current;
  }
  globalThis.SparkLinkReferences={scopeFor};
})();
