import { createSlice, PayloadAction } from "@reduxjs/toolkit";
import {
    fetchCommunityPosts,
    createCommunityPost,
    toggleLikeCommunityPost,
    toggleSaveCommunityPost,
    addCommunityComment,
    deleteCommunityPost,
} from "./community.api";

export interface CommentItem {
    id: string;
    postId?: string;
    userId?: number;
    authorName: string;
    authorAvatar?: string | null;
    authorBadge?: string;
    content: string;
    createdAt: string;
    likes: number;
}

export interface CommunityPost {
    id: string;
    userId?: number;
    authorName: string;
    authorAvatar?: string | null;
    authorRole?: string;
    authorBadge?: "Chuyên gia" | "AI Analyst" | "VIP Trader" | "Thành viên" | string;
    title?: string;
    content: string;
    symbol?: string;
    stance?: "BUY" | "SELL" | "HOLD" | "ANALYSIS" | string;
    targetPrice?: number;
    stopLossPrice?: number;
    category: "hot" | "signal" | "technical" | "fundamental" | "qa" | string;
    sector?: string;
    imageUrl?: string;
    createdAt: string;
    likes: number;
    commentsCount: number;
    viewsCount: number;
    isLiked?: boolean;
    isSaved?: boolean;
    comments: CommentItem[];
}

interface CommunityState {
    posts: CommunityPost[];
    total: number;
    loading: boolean;
    posting: boolean;
    commenting: boolean;
    error: string | null;
}

const initialState: CommunityState = {
    posts: [],
    total: 0,
    loading: false,
    posting: false,
    commenting: false,
    error: null,
};

export const communitySlice = createSlice({
    name: "community",
    initialState,
    reducers: {
        optimisticToggleLike: (state, action: PayloadAction<{ postId: string }>) => {
            const post = state.posts.find((p) => p.id === action.payload.postId);
            if (post) {
                post.isLiked = !post.isLiked;
                post.likes = post.isLiked ? post.likes + 1 : Math.max(0, post.likes - 1);
            }
        },
        optimisticToggleSave: (state, action: PayloadAction<{ postId: string }>) => {
            const post = state.posts.find((p) => p.id === action.payload.postId);
            if (post) {
                post.isSaved = !post.isSaved;
            }
        },
    },
    extraReducers: (builder) => {
        // Fetch posts
        builder
            .addCase(fetchCommunityPosts.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchCommunityPosts.fulfilled, (state, action) => {
                state.loading = false;
                state.posts = action.payload?.posts || [];
                state.total = action.payload?.total || 0;
            })
            .addCase(fetchCommunityPosts.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload as string;
            });

        // Create post
        builder
            .addCase(createCommunityPost.pending, (state) => {
                state.posting = true;
            })
            .addCase(createCommunityPost.fulfilled, (state, action) => {
                state.posting = false;
                if (action.payload) {
                    state.posts.unshift(action.payload);
                    state.total += 1;
                }
            })
            .addCase(createCommunityPost.rejected, (state, action) => {
                state.posting = false;
                state.error = action.payload as string;
            });

        // Toggle like sync
        builder.addCase(toggleLikeCommunityPost.fulfilled, (state, action) => {
            const { postId, isLiked, likesCount } = action.payload;
            const post = state.posts.find((p) => p.id === postId);
            if (post) {
                post.isLiked = isLiked;
                if (typeof likesCount === "number") {
                    post.likes = likesCount;
                }
            }
        });

        // Toggle save sync
        builder.addCase(toggleSaveCommunityPost.fulfilled, (state, action) => {
            const { postId, isSaved } = action.payload;
            const post = state.posts.find((p) => p.id === postId);
            if (post) {
                post.isSaved = isSaved;
            }
        });

        // Add comment
        builder
            .addCase(addCommunityComment.pending, (state) => {
                state.commenting = true;
            })
            .addCase(addCommunityComment.fulfilled, (state, action) => {
                state.commenting = false;
                const { postId, comment } = action.payload;
                const post = state.posts.find((p) => p.id === postId);
                if (post && comment) {
                    post.commentsCount += 1;
                    post.comments.push(comment);
                }
            })
            .addCase(addCommunityComment.rejected, (state, action) => {
                state.commenting = false;
                state.error = action.payload as string;
            });

        // Delete post
        builder.addCase(deleteCommunityPost.fulfilled, (state, action) => {
            const postId = action.payload;
            state.posts = state.posts.filter((p) => p.id !== postId);
            state.total = Math.max(0, state.total - 1);
        });
    },
});

export const { optimisticToggleLike, optimisticToggleSave } = communitySlice.actions;
export default communitySlice.reducer;
