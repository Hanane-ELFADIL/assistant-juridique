const B='';const h=t=>t?{Authorization:`Bearer ${t}`,'Content-Type':'application/json'}:{'Content-Type':'application/json'};
async function r(m,p,b,t){const res=await fetch(B+p,{method:m,headers:h(t),body:b?JSON.stringify(b):undefined});if(!res.ok){const e=await res.json().catch(()=>({}));throw new Error(e.detail||`Erreur ${res.status}`)}return res.json()}
export const api={
  register:d=>r('POST','/api/auth/register',d),
  login:d=>r('POST','/api/auth/login',d),
  me:t=>r('GET','/api/auth/me',null,t),
  health:()=>fetch('/health').then(x=>x.json()).catch(()=>({status:'error'})),
  chat:(q,t)=>r('POST','/api/chat',{question:q,n_results:8},t),
  getConversations:t=>r('GET','/api/user/conversations',null,t),
  getConversation:(id,t)=>r('GET',`/api/user/conversations/${id}`,null,t),
  deleteConversation:(id,t)=>r('DELETE',`/api/user/conversations/${id}`,null,t),
  saveMessage:(d,t)=>r('POST','/api/user/messages',d,t),
  getFavorites:t=>r('GET','/api/user/favorites',null,t),
  addFavorite:(d,t)=>r('POST','/api/user/favorites',d,t),
  removeFavorite:(id,t)=>r('DELETE',`/api/user/favorites/${id}`,null,t),
}
