(function(){
  const escV2=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const svgNS='http://www.w3.org/2000/svg';
  const card=(item,index)=>`<div class="v2-card" data-number="${String(index+1).padStart(2,'0')}"><div class="v2-label">${escV2(item.label)}</div>${item.detail?`<div class="v2-detail">${escV2(item.detail)}</div>`:''}</div>`;
  function graph(host,data){
    const svg=d3.select(host).append('svg').attr('viewBox','0 0 1740 620').attr('class','v2-graphic');
    const items=data.items,coords=new Map();
    const process=data.kind==='process';
    let width=process?Math.min(390,1620/items.length-28):430,height=process?290:230;
    if(process){items.forEach((item,i)=>coords.set(item.id,{x:70+i*(1600/Math.max(1,items.length-1)),y:300}));
      if(items.length===1)coords.set(items[0].id,{x:870,y:300});
      // Keep first/last node inside the drawing area.
      items.forEach((item,i)=>coords.set(item.id,{x:width/2+30+i*((1680-width)/Math.max(1,items.length-1)),y:300}));
    }else{
      const incoming=new Map((data.edges||[]).map(edge=>[edge.to_id,edge.from_id]));
      const roots=items.filter(item=>!incoming.has(item.id));
      const raw=items.map(item=>({id:item.id,parent:incoming.get(item.id)|| (roots.length>1?'__root__':null)}));
      if(roots.length>1)raw.push({id:'__root__',parent:null});
      const tree=d3.stratify().id(node=>node.id).parentId(node=>node.parent)(raw);
      d3.tree().size([1420,400])(tree);
      const visible=tree.descendants().filter(node=>node.id!=='__root__');
      const levels=d3.group(visible,node=>node.depth);
      const breadth=Math.max(...Array.from(levels.values(),nodes=>nodes.length));
      width=Math.min(430,1500/Math.max(1,breadth)-30);
      const minDepth=Math.min(...visible.map(node=>node.depth)),maxDepth=Math.max(...visible.map(node=>node.depth));
      const drawingHeight=Math.max(620,280+(maxDepth-minDepth)*260);
      svg.attr('viewBox',`0 0 1740 ${drawingHeight}`);
      visible.forEach(node=>coords.set(node.id,{x:node.x+160,y:140+(node.depth-minDepth)*260}));
    }
    const edges=svg.append('g');
    (data.edges||[]).forEach(edge=>{
      const a=coords.get(edge.from_id),b=coords.get(edge.to_id);if(!a||!b)return;
      const start=process?[a.x+width/2,a.y]:[a.x,a.y+height/2];
      const end=process?[b.x-width/2,b.y]:[b.x,b.y-height/2];
      const link=process?d3.linkHorizontal():d3.linkVertical();
      edges.append('path').attr('class','v2-edge').attr('d',link({source:start,target:end}));
    });
    items.forEach((item,index)=>{
      const position=coords.get(item.id);if(!position)return;
      const positionGroup=svg.append('g').attr('transform',`translate(${position.x-width/2},${position.y-height/2})`);
      const node=positionGroup.append('g').attr('class','v2-graph-node');
      node.append('rect').attr('class','v2-node-box').attr('width',width).attr('height',height).attr('rx',4);
      node.append('rect').attr('width',width).attr('height',4).attr('fill','#D52B1E');
      const foreign=node.append('foreignObject').attr('x',0).attr('y',process?42:0).attr('width',width).attr('height',height-(process?42:0));
      const div=document.createElement('div');div.setAttribute('xmlns','http://www.w3.org/1999/xhtml');div.className='v2-node';
      div.innerHTML=`<div class="v2-label">${escV2(item.label)}</div>${item.detail?`<div class="v2-detail">${escV2(item.detail)}</div>`:''}`;
      foreign.node().appendChild(div);
      if(process){node.append('circle').attr('class','v2-step').attr('cx',27).attr('cy',28).attr('r',18);
        node.append('text').attr('class','v2-step-label').attr('x',27).attr('y',36).attr('text-anchor','middle').text(index+1);}
    });
    return svg.node();
  }
  function build(el,data,tl){
    el.innerHTML=`<div class="v2-kicker">${escV2(data.kicker||'Gestión Discrecional · incorporación')}</div><div class="v2-title">${escV2(data.title)}</div><div class="v2-divider"></div><div class="v2-panel"></div>`;
    const heading=el.querySelector('.v2-title');
    let headingSize=58;
    while(heading.getBoundingClientRect().height>88&&headingSize>36){headingSize-=2;heading.style.fontSize=headingSize+'px';}
    const panel=el.querySelector('.v2-panel');
    if(['organisation','process'].includes(data.kind)){graph(panel,data);}
    else if(['hero','close','illustration'].includes(data.kind)&&data.image_url){
      panel.classList.add(data.kind);
      panel.innerHTML=`<div class="v2-hero-copy">${data.items.map(card).join('')}</div><div class="v2-picture-wrap"><img class="v2-picture" src="${escV2(data.image_url)}"/><div class="v2-picture-note">Ilustración conceptual</div></div>`;
    }else{
      panel.classList.add(data.kind==='timeline'?'v2-timeline':['hero','close','focus'].includes(data.kind)?'v2-focus':'v2-map',`count-${data.items.length}`);
      if(['hero','close'].includes(data.kind))panel.classList.add('v2-opening');
      panel.innerHTML=data.items.map(card).join('');
    }
    const animation=gsap.timeline({paused:true});
    animation.fromTo(el.querySelector('.v2-title'),{opacity:0,y:18},{opacity:1,y:0,duration:.6,ease:'power2.out'},.1);
    animation.fromTo(el.querySelector('.v2-kicker'),{opacity:0},{opacity:1,duration:.4},.05);
    animation.fromTo(el.querySelector('.v2-divider'),{scaleX:0},{scaleX:1,duration:.8,ease:'power2.out'},.2);
    const blocks=[...el.querySelectorAll('.v2-card,.v2-graph-node')];
    blocks.forEach((node,index)=>animation.fromTo(node,{opacity:0,y:12},{opacity:1,y:0,duration:.55,ease:'power2.out'},.6+index*.2));
    el.querySelectorAll('.v2-edge').forEach((path,index)=>{
      const length=path.getTotalLength();path.style.strokeDasharray=length;
      animation.fromTo(path,{strokeDashoffset:length},{strokeDashoffset:0,duration:1,ease:'power1.inOut'},.9+index*.35);
    });
    const picture=el.querySelector('.v2-picture');
    if(picture){animation.fromTo(picture,{opacity:0,scale:.97},{opacity:1,scale:1,duration:1.2,ease:'power2.out'},.45);
      animation.to(picture,{scale:1.015,duration:Math.max(1,tl.duration-2),ease:'none'},1.7);}
    if(data.movement==='focus'&&blocks.length>1){
      blocks.forEach((node,index)=>{const start=2+index*(Math.max(1,tl.duration-4)/blocks.length);
        animation.to(node,{borderColor:'#D52B1E',boxShadow:'0 0 0 1px #D52B1E',duration:.3},start);
        animation.to(node,{borderColor:'#D5D2CE',boxShadow:'0 0 0 0px #D52B1E',duration:.3},Math.min(tl.duration-.5,start+2));});
    }
    if(data.transition==='diagonal'){
      const wipe=document.createElement('div');wipe.className='v2-wipe';el.appendChild(wipe);
      animation.fromTo(wipe,{x:-2500,skewX:-17},{x:2500,skewX:-17,duration:.8,ease:'power2.inOut'},0);
    }else if(data.transition==='slide'){
      animation.fromTo(panel,{x:55},{x:0,duration:.75,ease:'power2.out'},.1);
    }
    return animation;
  }
  window.onboardingV2={build,graph};
})();
